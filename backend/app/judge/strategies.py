"""EvalStrategy classes — prompt construction and output parsing per strategy."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from app.judge import PromptContext


_sandbox_env = SandboxedEnvironment(undefined=StrictUndefined)


def _render_jinja(template: str, ctx: PromptContext) -> str:
    """Render a Jinja2 template with sandboxed environment."""
    try:
        tpl = _sandbox_env.from_string(template)
        return tpl.render(**asdict(ctx))
    except TemplateError:
        raise


# ── Strategy interface ──────────────────────────────────────────────────────

class EvalStrategy(ABC):
    """Base class for evaluation prompt strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier."""

    @abstractmethod
    def build_prompt(self, ctx: PromptContext,
                     system_prompt: str | None,
                     user_template: str | None) -> tuple[str, str]:
        """Build (system_prompt, user_prompt) for LLM invocation."""

    @abstractmethod
    def parse_response(self, raw: str, schema: dict | None) -> dict:
        """Parse LLM response into structured result dict.

        Returns dict with keys: score, reasoning, dimension_scores (optional).
        """

    @property
    def default_system_prompt(self) -> str:
        return "You are an expert AI evaluation judge."

    @property
    def default_user_template(self) -> str:
        return (
            "## Input\n{{input}}\n\n"
            "## Actual Output\n{{actual_output}}\n\n"
            "Please provide a score between 0.0 and 1.0."
        )


# ── JSON parsing utility ───────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict | None:
    """Multi-layer JSON extraction from LLM response."""
    # Layer 1: strict JSON parse
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Layer 2: extract JSON from markdown code block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # Layer 3: regex extraction of score field
    score_m = re.search(r'(?:score|rating):\s*([0-9]*\.?[0-9]+)', raw, re.I)
    if score_m:
        reasoning_m = re.search(
            r'(?:reasoning|analysis|explanation):\s*(.+?)(?:\n|$)',
            raw, re.I | re.DOTALL
        )
        return {
            "score": float(score_m.group(1)),
            "reasoning": reasoning_m.group(1).strip() if reasoning_m else raw[:500],
        }

    return None


# Fallback key names when schema doesn't specify an explicit key
_SCORE_FALLBACK_KEYS = ("score", "rating", "value", "result", "quality")
_TEXT_FALLBACK_KEYS = ("reasoning", "analysis", "explanation", "thought", "comment")
_DIM_FALLBACK_KEYS = ("dimension_scores", "dimensions", "scores", "sub_scores")


def _normalize_score(val: float) -> float:
    """Normalize a score into the [0.0, 1.0] range.

    - Values in (1.0, 100.0] are treated as a percentage and divided by 100.
    - Out-of-range values are clamped to [0.0, 1.0].
    """
    try:
        val = float(val)
    except (ValueError, TypeError):
        return 0.0
    if 1.0 < val <= 100.0:
        val = val / 100.0
    return max(0.0, min(1.0, val))


def _schema_keys(schema: dict | None, type_hint: str) -> list[str]:
    """Return candidate key names from schema whose value spec mentions type_hint.

    The schema format is ``{"<key>": "<type description>"}``. We return the keys
    whose spec string contains ``type_hint`` (e.g. "number", "string", "object"),
    preserving declaration order.
    """
    if not isinstance(schema, dict):
        return []
    keys: list[str] = []
    for key, spec in schema.items():
        spec_str = spec if isinstance(spec, str) else json.dumps(spec, ensure_ascii=False)
        if type_hint in spec_str.lower():
            keys.append(key)
    return keys


def _first_present(data: dict, keys: list[str]):
    """Return the first non-None value among keys (in order), else None."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _extract_number(data: dict, schema: dict | None) -> float:
    """Extract and normalize a numeric score from parsed data.

    Key resolution order:
      1. Keys declared in the schema whose spec mentions "number"/"score".
      2. Well-known fallback key names.
    """
    candidate_keys = _schema_keys(schema, "number")
    # Also accept keys explicitly named like a score in the schema
    if isinstance(schema, dict):
        candidate_keys += [k for k in schema if "score" in k.lower() and k not in candidate_keys]

    value = _first_present(data, candidate_keys) if candidate_keys else None
    if value is None:
        value = _first_present(data, list(_SCORE_FALLBACK_KEYS))
    if value is None:
        return 0.0
    return _normalize_score(value)


def _extract_text(data: dict, schema: dict | None) -> str:
    """Extract a text reasoning value from parsed data."""
    candidate_keys = _schema_keys(schema, "string")
    value = _first_present(data, candidate_keys) if candidate_keys else None
    if value is None:
        value = _first_present(data, list(_TEXT_FALLBACK_KEYS))
    return str(value) if value else ""


def _extract_dimensions(data: dict, schema: dict | None) -> dict[str, float]:
    """Extract dimension scores from parsed data.

    Key resolution order:
      1. Keys declared in the schema whose spec mentions "object"/"dimension".
      2. Well-known fallback key names.
    """
    candidate_keys = _schema_keys(schema, "object") + _schema_keys(schema, "dimension")
    value = _first_present(data, candidate_keys) if candidate_keys else None
    if value is None:
        value = _first_present(data, list(_DIM_FALLBACK_KEYS))
    # Schema may name a specific dimension key that holds a plain number
    if not isinstance(value, dict) and isinstance(data, dict):
        collected: dict[str, float] = {}
        for key in (candidate_keys or []):
            v = data.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                collected[key] = _normalize_score(v)
        if collected:
            return collected
    if isinstance(value, dict):
        return {k: _normalize_score(v) for k, v in value.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    return {}


def parse_by_schema(raw: str, schema: dict | None) -> dict:
    """Unified schema-driven response parser shared by all strategies.

    Returns dict with keys: score (normalized to [0,1]), reasoning, dimension_scores.
    """
    parsed = _parse_json_response(raw)
    if not parsed:
        return {"score": 0.0, "reasoning": raw[:500], "dimension_scores": {}}
    return {
        "score": _extract_number(parsed, schema),
        "reasoning": _extract_text(parsed, schema) or str(parsed.get("reasoning", "") or ""),
        "dimension_scores": _extract_dimensions(parsed, schema),
    }


# ── Strategy Implementations ───────────────────────────────────────────────

class SimpleStrategy(EvalStrategy):
    """General-purpose scoring — evaluate response quality."""

    @property
    def name(self) -> str:
        return "simple"

    @property
    def default_user_template(self) -> str:
        return (
            "## Input\n{{input}}\n\n"
            "## Actual Output\n{{actual_output}}\n\n"
            "{% if criteria %}\n## Criteria\n{{criteria}}\n{% endif %}\n\n"
            "Evaluate the response quality. Provide a score between 0.0 and 1.0.\n\n"
            "## Output Format\n"
            "```json\n"
            "{\n"
            '  "reasoning": "Your analysis...",\n'
            '  "score": 0.85\n'
            "}\n"
            "```"
        )

    def build_prompt(self, ctx: PromptContext,
                     system_prompt: str | None,
                     user_template: str | None) -> tuple[str, str]:
        sp = system_prompt or self.default_system_prompt
        ut = user_template or self.default_user_template
        up = _render_jinja(ut, ctx)
        return sp, up

    def parse_response(self, raw: str, schema: dict | None) -> dict:
        return parse_by_schema(raw, schema)


class ReferenceStrategy(EvalStrategy):
    """Reference-based scoring — compare actual output with expected output."""

    @property
    def name(self) -> str:
        return "reference"

    @property
    def default_system_prompt(self) -> str:
        return (
            "你是一位资深的 AI 回复质量评估专家，负责将 AI 智能体的实际输出与参考答案进行严谨对比，并给出客观评分。\n"
            "你的评分必须基于事实与标准答案，逻辑清晰、标准一致——同样的对比结果在任何情况下都应得到相近的分数。\n"
            "评分范围严格限定在 0.0 到 1.0 之间。"
        )

    @property
    def default_user_template(self) -> str:
        return (
            "## 任务说明\n请将 AI 智能体的实际输出与参考答案进行对比，评估其匹配程度并给出 0.0-1.0 的评分。\n\n"
            "## 用户输入\n{{input}}\n\n"
            "{% if expected_output %}\n## 参考答案\n以下是为该问题准备的标准答案：\n{{expected_output}}\n{% else %}\n## 参考答案\n（本次未提供参考答案，请仅依据用户输入与实际输出，从内容质量角度进行评判。）\n{% endif %}\n\n"
            "{% if criteria %}\n## 评分准则\n请重点依据以下准则进行评判：\n{{criteria}}\n{% endif %}\n\n"
            "## 实际输出\n以下是被评估的 AI 智能体的实际回复：\n{{actual_output}}\n\n"
            "## 对比要求\n请逐项对比实际输出与参考答案，明确指出：\n"
            "1. **命中部分**：实际输出中与参考答案一致或等价的要点\n"
            "2. **遗漏部分**：参考答案中有、但实际输出缺失的要点\n"
            "3. **偏差部分**：实际输出中与参考答案矛盾、错误或多余的内容\n\n"
            "## 评分维度（供参考，可结合评分准则调整）\n"
            "1. **准确性**：与参考答案相比，事实与结论是否正确\n"
            "2. **完整性**：是否覆盖了参考答案的全部关键要点\n"
            "3. **清晰度**：表达是否通顺、结构是否清晰\n\n"
            "## 评分标准\n"
            "- **0.9-1.0**：与参考答案高度一致，要点齐全，无实质偏差\n"
            "- **0.7-0.9**：主要要点一致，存在少量遗漏或不精确\n"
            "- **0.5-0.7**：部分要点命中，但有明显遗漏或偏差\n"
            "- **0.3-0.5**：仅少量要点相符，大部分缺失或错误\n"
            "- **0.0-0.3**：与参考答案基本不符或严重偏离\n\n"
            "## 扣分项\n出现以下情况时，应在对应维度上酌情扣分：\n"
            "- **事实性错误**：与参考答案矛盾，或包含明显错误的事实、数据、结论，扣分从重\n"
            "- **要点遗漏**：参考答案中的关键要点未覆盖，按缺失程度扣分\n"
            "- **答非所问**：未回应用户的真实问题或意图，大幅扣分\n"
            "- **过度发挥**：加入大量参考答案之外且无关的内容，酌情扣分\n"
            "- **有害或不当内容**：包含不当、歧视性或有害表述，严重扣分\n\n"
            "## 输出要求\n"
            "请先给出对比分析（命中/遗漏/偏差），再给出最终评分。必须严格按照以下 JSON 格式输出，不要包含其他内容：\n"
            '```json\n'
            "{\n"
            '  "reasoning": "对比分析：命中...；遗漏...；偏差...",\n'
            '  "score": 0.85,\n'
            '  "dimension_scores": {\n'
            '    "准确性": 0.9,\n'
            '    "完整性": 0.8,\n'
            '    "清晰度": 0.85\n'
            "  }\n"
            "}\n"
            "```"
        )

    def build_prompt(self, ctx: PromptContext,
                     system_prompt: str | None,
                     user_template: str | None) -> tuple[str, str]:
        sp = system_prompt or self.default_system_prompt
        ut = user_template or self.default_user_template
        up = _render_jinja(ut, ctx)
        return sp, up

    def parse_response(self, raw: str, schema: dict | None) -> dict:
        return parse_by_schema(raw, schema)


class RubricStrategy(EvalStrategy):
    """Multi-dimension rubric-based scoring."""

    @property
    def name(self) -> str:
        return "rubric"

    @property
    def default_system_prompt(self) -> str:
        return (
            "你是一位资深的 AI 回复质量评估专家，负责依据评分规约对 AI 智能体的输出进行多维度、客观的打分。\n"
            "你必须严格按照评分规约中定义的每个维度逐项评估，评分标准一致——同样的输出在任何情况下都应得到相近的分数。\n"
            "评分范围严格限定在 0.0 到 1.0 之间。"
        )

    @property
    def default_user_template(self) -> str:
        return (
            "## 任务说明\n请依据下方的评分规约，对 AI 智能体的输出进行多维度评估，给出各项维度得分及加权总分。\n\n"
            "## 用户输入\n{{input}}\n\n"
            "{% if expected_output %}\n## 参考答案\n以下是为该问题准备的标准答案，可作为评判依据之一：\n{{expected_output}}\n{% endif %}\n\n"
            "## 实际输出\n以下是被评估的 AI 智能体的实际回复：\n{{actual_output}}\n\n"
            "{% if rubric %}\n## 评分规约\n请严格按照以下规约逐维度打分：\n{{rubric}}\n{% else %}\n## 评分规约\n请从以下维度进行评估：\n"
            "1. **准确性**：内容是否事实正确、无明显错误\n"
            "2. **完整性**：是否覆盖了问题的关键要点\n"
            "3. **清晰度**：表达是否通顺、条理清晰\n"
            "{% endif %}\n\n"
            "## 评分要求\n"
            "1. **逐维度独立评估**：对上述每个维度，独立给出 0.0-1.0 的分数\n"
            "2. **加权总分**：若规约中标注了维度权重，按权重计算加权总分；否则取各维度平均分\n"
            "3. **评分一致性**：各维度得分需有明确依据\n\n"
            "## 评分标准（适用于每个维度）\n"
            "- **0.9-1.0**：该维度表现优秀，无明显缺陷\n"
            "- **0.7-0.9**：该维度表现良好，有少量不足\n"
            "- **0.5-0.7**：该维度表现一般，存在明显问题\n"
            "- **0.3-0.5**：该维度表现较差，缺陷较多\n"
            "- **0.0-0.3**：该维度表现很差或完全不满足\n\n"
            "## 扣分项\n出现以下情况时，应在相关维度上酌情扣分：\n"
            "- **事实性错误**：包含明显错误的事实、数据或结论，扣分从重\n"
            "- **维度缺失**：某个评分维度完全未满足，该维度大幅扣分\n"
            "- **答非所问**：未回应用户的真实问题或意图，大幅扣分\n"
            "- **有害或不当内容**：包含不当、歧视性或有害表述，严重扣分\n\n"
            "## 输出要求\n"
            "请先给出各维度的分析理由，再给出维度得分与加权总分。必须严格按照以下 JSON 格式输出：\n"
            '```json\n'
            "{\n"
            '  "reasoning": "各维度分析：...",\n'
            '  "score": 0.85,\n'
            '  "dimension_scores": {\n'
            '    "准确性": 0.9,\n'
            '    "完整性": 0.8,\n'
            '    "清晰度": 0.85\n'
            "  }\n"
            "}\n"
            "```"
        )

    def build_prompt(self, ctx: PromptContext,
                     system_prompt: str | None,
                     user_template: str | None) -> tuple[str, str]:
        sp = system_prompt or self.default_system_prompt
        ut = user_template or self.default_user_template
        up = _render_jinja(ut, ctx)
        return sp, up

    def parse_response(self, raw: str, schema: dict | None) -> dict:
        return parse_by_schema(raw, schema)


class ChainOfThoughtStrategy(EvalStrategy):
    """Chain-of-thought scoring — reason step-by-step before scoring."""

    @property
    def name(self) -> str:
        return "chain_of_thought"

    @property
    def default_system_prompt(self) -> str:
        return (
            "你是一位资深的 AI 回复质量评估专家，擅长通过严谨的分步推理，对 AI 智能体的输出进行客观、可信的打分。\n"
            "你必须遵循「先推理、后结论」的原则：先按步骤逐条分析，再基于分析结果给出评分，保证评分的可解释性。\n"
            "评分范围严格限定在 0.0 到 1.0 之间。"
        )

    @property
    def default_user_template(self) -> str:
        return (
            "## 任务说明\n请通过分步推理，评估 AI 智能体针对用户问题的回复质量，并给出 0.0-1.0 的评分。\n\n"
            "## 评估材料\n"
            "### 用户输入\n{{input}}\n\n"
            "{% if expected_output %}"
            "### 参考答案\n以下是为该问题准备的标准答案，可作为评判依据：\n{{expected_output}}\n\n"
            "{% endif %}"
            "{% if criteria %}"
            "### 评分准则\n请重点依据以下准则进行评判：\n{{criteria}}\n\n"
            "{% endif %}"
            "### 实际输出\n以下是被评估的 AI 智能体的实际回复：\n{{actual_output}}\n\n"
            "## 推理步骤\n请严格按照以下步骤逐步分析，不要跳步：\n\n"
            "**第 1 步 · 理解任务**\n说明用户问题的核心诉求是什么，一个理想回答应包含哪些关键要点。\n\n"
            "**第 2 步 · 核查事实**\n逐条检查实际输出中的事实、数据、结论是否正确，是否有明显错误或幻觉。\n\n"
            "**第 3 步 · 评估完整性**\n对照用户诉求（或参考答案），判断实际输出覆盖了哪些要点、遗漏了哪些要点。\n\n"
            "**第 4 步 · 评估表达**\n判断实际输出的结构、逻辑与表述是否清晰、有条理。\n\n"
            "**第 5 步 · 综合定分**\n综合以上分析，给出最终评分，并说明该分数落在哪个档位、为什么。\n\n"
            "## 评分标准\n"
            "- **0.9-1.0**：优秀，准确完整，无明显缺陷\n"
            "- **0.7-0.9**：良好，基本正确，有少量不足\n"
            "- **0.5-0.7**：一般，存在明显缺漏或部分错误\n"
            "- **0.3-0.5**：较差，有较多错误或信息缺失\n"
            "- **0.0-0.3**：很差，答非所问或严重错误\n\n"
            "## 扣分项\n出现以下情况时，应酌情扣分：\n"
            "- **事实性错误**：包含明显错误的事实、数据或结论，扣分从重\n"
            "- **答非所问**：未回应用户的真实问题或意图，大幅扣分\n"
            "- **信息缺失**：遗漏关键要点或必要信息，按缺失程度扣分\n"
            "- **逻辑混乱**：推理过程前后矛盾、条理不清，酌情扣分\n\n"
            "## 输出要求\n"
            "`reasoning` 字段中请完整保留上述 5 个步骤的分析过程。必须严格按照以下 JSON 格式输出，不要包含其他内容：\n"
            '```json\n'
            "{\n"
            '  "reasoning": "第1步：...\\n第2步：...\\n第3步：...\\n第4步：...\\n第5步：...",\n'
            '  "score": 0.85\n'
            "}\n"
            "```"
        )

    def build_prompt(self, ctx: PromptContext,
                     system_prompt: str | None,
                     user_template: str | None) -> tuple[str, str]:
        sp = system_prompt or self.default_system_prompt
        ut = user_template or self.default_user_template
        up = _render_jinja(ut, ctx)
        return sp, up

    def parse_response(self, raw: str, schema: dict | None) -> dict:
        return parse_by_schema(raw, schema)


class FewShotStrategy(EvalStrategy):
    """Few-shot scoring — provide examples in the prompt."""

    @property
    def name(self) -> str:
        return "few_shot"

    @property
    def default_system_prompt(self) -> str:
        return (
            "你是一位资深的 AI 回复质量评估专家，负责参考已给定的评分示例，对 AI 智能体的输出进行客观、严谨的打分。\n"
            "你必须保持与示例一致的评分标准与尺度——产出与示例相似的质量应得到相近的分数。\n"
            "评分范围严格限定在 0.0 到 1.0 之间。"
        )

    @property
    def default_user_template(self) -> str:
        return (
            "{% if few_shot_examples %}"
            "## 评分参考示例\n"
            "以下是若干已标注好分数的示例，请仔细体会其中的评分尺度与标准：\n"
            "{% for ex in few_shot_examples %}"
            "### 示例 {{ loop.index }}\n"
            "- 用户输入：{{ ex.input }}\n"
            "{% if ex.expected_output %}- 参考答案：{{ ex.expected_output }}\n{% endif %}"
            "- 实际输出：{{ ex.actual_output }}\n"
            "- 评分：{{ ex.score }}（0.0-1.0 之间的分数）\n"
            "- 评分理由：{{ ex.reasoning }}\n\n"
            "{% endfor %}"
            "{% else %}"
            "## 提示\n本次未提供评分示例，请依据通用的质量评估标准进行判断。\n"
            "{% endif %}"
            "\n## 待评估内容\n"
            "### 用户输入\n{{input}}\n\n"
            "### 实际输出\n{{actual_output}}\n\n"
            "{% if expected_output %}"
            "### 参考答案\n{{expected_output}}\n\n"
            "{% endif %}"
            "{% if criteria %}\n## 评分准则\n请重点依据以下准则进行评判：\n{{criteria}}\n{% endif %}\n\n"
            "## 评分要求\n请参考上方示例的评分尺度，保持标准一致。评分范围严格为 0.0 到 1.0。\n\n"
            "## 评分标准\n"
            "- **0.9-1.0**：优秀，准确完整，无明显缺陷\n"
            "- **0.7-0.9**：良好，基本正确，有少量不足\n"
            "- **0.5-0.7**：一般，存在明显缺漏或部分错误\n"
            "- **0.3-0.5**：较差，有较多错误或信息缺失\n"
            "- **0.0-0.3**：很差，答非所问或严重错误\n\n"
            "## 扣分项\n出现以下情况时，应酌情扣分：\n"
            "- **事实性错误**：包含明显错误的事实、数据或结论，扣分从重\n"
            "- **与示例尺度不一致**：评分明显偏离示例所示的尺度，需自我校正\n"
            "- **答非所问**：未回应用户的真实问题或意图，大幅扣分\n"
            "- **信息缺失**：遗漏关键要点或必要信息，按缺失程度扣分\n\n"
            "## 输出要求\n"
            "请先简要说明评分理由，再给出最终评分。必须严格按照以下 JSON 格式输出，不要包含其他内容：\n"
            '```json\n{"reasoning": "评分理由...", "score": 0.85}\n```'
        )

    def build_prompt(self, ctx: PromptContext,
                     system_prompt: str | None,
                     user_template: str | None) -> tuple[str, str]:
        sp = system_prompt or self.default_system_prompt
        ut = user_template or self.default_user_template
        up = _render_jinja(ut, ctx)
        return sp, up

    def parse_response(self, raw: str, schema: dict | None) -> dict:
        return parse_by_schema(raw, schema)


class PairwiseStrategy(EvalStrategy):
    """Pairwise comparison — choose the better of two outputs."""

    @property
    def name(self) -> str:
        return "pairwise"

    @property
    def default_system_prompt(self) -> str:
        return "You are an expert AI evaluation judge. Compare two AI responses and choose the better one."

    @property
    def default_user_template(self) -> str:
        return (
            "## Input\n{{input}}\n\n"
            "## Response A\n{{actual_output}}\n\n"
            "## Response B\n{{pairwise_alternative}}\n\n"
            "Analyze both responses and determine which is better.\n"
            "Provide your reasoning and a score for each response (0.0-1.0).\n\n"
            "## Output Format\n"
            "```json\n"
            "{\n"
            '  "reasoning": "Comparative analysis...",\n'
            '  "score": 0.85,\n'
            '  "dimension_scores": {\n'
            '    "response_a_score": 0.85,\n'
            '    "response_b_score": 0.72,\n'
            '    "preference": "A"\n'
            "  }\n"
            "}\n"
            "```"
        )

    def build_prompt(self, ctx: PromptContext,
                     system_prompt: str | None,
                     user_template: str | None) -> tuple[str, str]:
        sp = system_prompt or self.default_system_prompt
        ut = user_template or self.default_user_template
        up = _render_jinja(ut, ctx)
        return sp, up

    def parse_response(self, raw: str, schema: dict | None) -> dict:
        return parse_by_schema(raw, schema)


# ── Strategy registry ──────────────────────────────────────────────────────

STRATEGY_REGISTRY: dict[str, type[EvalStrategy]] = {
    "simple": SimpleStrategy,
    "reference": ReferenceStrategy,
    "rubric": RubricStrategy,
    "chain_of_thought": ChainOfThoughtStrategy,
    "few_shot": FewShotStrategy,
    "pairwise": PairwiseStrategy,
}


def get_strategy(name: str) -> EvalStrategy:
    """Get a strategy instance by name."""
    cls = STRATEGY_REGISTRY.get(name, SimpleStrategy)
    return cls()
