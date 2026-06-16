"""EvalStrategy classes — prompt construction and output parsing per strategy."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Any

from jinja2 import Template, StrictUndefined, TemplateError
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


def _extract_number(data: dict, spec: str) -> float:
    """Extract a numeric value from parsed data according to schema spec."""
    if isinstance(spec, str) and "number" in spec:
        for key in ("score", "rating", "value", "result"):
            val = data.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
    return 0.0


def _extract_text(data: dict, spec: str) -> str:
    """Extract a text value from parsed data according to schema spec."""
    if isinstance(spec, str) and "string" in spec:
        for key in ("reasoning", "analysis", "explanation", "thought", "comment"):
            val = data.get(key)
            if val:
                return str(val)
    return ""


def _extract_dimensions(data: dict, spec: Any) -> dict[str, float]:
    """Extract dimension scores from parsed data."""
    for key in ("dimension_scores", "dimensions", "scores", "sub_scores"):
        val = data.get(key)
        if isinstance(val, dict):
            return {k: float(v) for k, v in val.items() if isinstance(v, (int, float))}
    return {}


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
        parsed = _parse_json_response(raw)
        if not parsed:
            return {"score": 0.0, "reasoning": raw[:500]}

        if schema:
            return {
                "score": _extract_number(parsed, schema.get("score", "number")),
                "reasoning": _extract_text(parsed, schema.get("reasoning", "string")),
                "dimension_scores": _extract_dimensions(parsed, schema.get("dimensions", {})),
            }

        return {
            "score": float(parsed.get("score", 0.0)),
            "reasoning": str(parsed.get("reasoning", "") or parsed.get("explanation", "")),
            "dimension_scores": _extract_dimensions(parsed, None),
        }


class ReferenceStrategy(EvalStrategy):
    """Reference-based scoring — compare actual output with expected output."""

    @property
    def name(self) -> str:
        return "reference"

    @property
    def default_system_prompt(self) -> str:
        return "You are an expert AI evaluation judge. Compare the actual output with the expected output (reference)."

    @property
    def default_user_template(self) -> str:
        return (
            "## Input\n{{input}}\n\n"
            "## Expected Output (Reference)\n{{expected_output}}\n\n"
            "## Actual Output\n{{actual_output}}\n\n"
            "Score how well the actual output matches the expected output in terms of:\n"
            "- Accuracy: Does it contain the correct information?\n"
            "- Completeness: Does it cover all aspects of the expected output?\n"
            "- Clarity: Is it well-structured and clear?\n\n"
            "Provide a score between 0.0 and 1.0.\n\n"
            "## Output Format\n"
            "```json\n"
            "{\n"
            '  "reasoning": "Your comparative analysis...",\n'
            '  "score": 0.85,\n'
            '  "dimension_scores": {\n'
            '    "accuracy": 0.9,\n'
            '    "completeness": 0.8,\n'
            '    "clarity": 0.85\n'
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
        parsed = _parse_json_response(raw)
        if not parsed:
            return {"score": 0.0, "reasoning": raw[:500]}

        return {
            "score": float(parsed.get("score", 0.0)),
            "reasoning": str(parsed.get("reasoning", "")),
            "dimension_scores": (
                parsed.get("dimension_scores")
                or parsed.get("dimensions")
                or {}
            ),
        }


class RubricStrategy(EvalStrategy):
    """Multi-dimension rubric-based scoring."""

    @property
    def name(self) -> str:
        return "rubric"

    @property
    def default_system_prompt(self) -> str:
        return "You are an expert AI evaluation judge. Score the response using the provided rubric."

    @property
    def default_user_template(self) -> str:
        return (
            "## Input\n{{input}}\n\n"
            "## Actual Output\n{{actual_output}}\n\n"
            "{% if expected_output %}"
            "## Expected Output (Reference)\n{{expected_output}}\n\n"
            "{% endif %}"
            "## Scoring Rubric\n{{rubric}}\n\n"
            "Score each dimension in the rubric independently, then provide a weighted overall score.\n\n"
            "## Output Format\n"
            "```json\n"
            "{\n"
            '  "reasoning": "Your analysis for each dimension...",\n'
            '  "score": 0.85,\n'
            '  "dimension_scores": {\n'
            '    "dimension_name": 0.9\n'
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
        parsed = _parse_json_response(raw)
        if not parsed:
            return {"score": 0.0, "reasoning": raw[:500]}

        return {
            "score": float(parsed.get("score", 0.0)),
            "reasoning": str(parsed.get("reasoning", "")),
            "dimension_scores": (
                parsed.get("dimension_scores")
                or parsed.get("dimensions")
                or {}
            ),
        }


class ChainOfThoughtStrategy(EvalStrategy):
    """Chain-of-thought scoring — reason step-by-step before scoring."""

    @property
    def name(self) -> str:
        return "chain_of_thought"

    @property
    def default_system_prompt(self) -> str:
        return "You are an expert AI evaluation judge. Before giving the final score, reason step-by-step."

    @property
    def default_user_template(self) -> str:
        return (
            "## Input\n{{input}}\n\n"
            "## Actual Output\n{{actual_output}}\n\n"
            "{% if expected_output %}"
            "## Expected Output (Reference)\n{{expected_output}}\n\n"
            "{% endif %}"
            "{% if criteria %}"
            "## Scoring Criteria\n{{criteria}}\n\n"
            "{% endif %}"
            "Please follow these steps:\n"
            "1. Understand the evaluation criteria\n"
            "2. Analyze the actual output's key elements\n"
            "3. Compare against expectations point by point\n"
            "4. Provide your reasoning and final score\n\n"
            "## Output Format\n"
            "```json\n"
            "{\n"
            '  "reasoning": "Step-by-step analysis...",\n'
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
        parsed = _parse_json_response(raw)
        if not parsed:
            return {"score": 0.0, "reasoning": raw[:500]}

        return {
            "score": float(parsed.get("score", 0.0)),
            "reasoning": str(parsed.get("reasoning", "") or raw[:500]),
            "dimension_scores": _extract_dimensions(parsed, None),
        }


class FewShotStrategy(EvalStrategy):
    """Few-shot scoring — provide examples in the prompt."""

    @property
    def name(self) -> str:
        return "few_shot"

    @property
    def default_system_prompt(self) -> str:
        return "You are an expert AI evaluation judge. Use the provided examples to guide your scoring."

    @property
    def default_user_template(self) -> str:
        return (
            "{% if few_shot_examples %}"
            "## Examples\n"
            "{% for ex in few_shot_examples %}"
            "### Example {{ loop.index }}\n"
            "Input: {{ ex.input }}\n"
            "{% if ex.expected_output %}Expected: {{ ex.expected_output }}\n{% endif %}"
            "Actual Output: {{ ex.actual_output }}\n"
            "Score: {{ ex.score }}\n"
            "Reasoning: {{ ex.reasoning }}\n\n"
            "{% endfor %}"
            "{% endif %}"
            "## Now evaluate the following\n"
            "### Input\n{{input}}\n\n"
            "### Actual Output\n{{actual_output}}\n\n"
            "{% if expected_output %}"
            "### Expected Output (Reference)\n{{expected_output}}\n\n"
            "{% endif %}"
            "Follow the format from the examples above.\n\n"
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
        parsed = _parse_json_response(raw)
        if not parsed:
            return {"score": 0.0, "reasoning": raw[:500]}

        return {
            "score": float(parsed.get("score", 0.0)),
            "reasoning": str(parsed.get("reasoning", "")),
            "dimension_scores": _extract_dimensions(parsed, None),
        }


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
        parsed = _parse_json_response(raw)
        if not parsed:
            return {"score": 0.0, "reasoning": raw[:500]}

        dims = (
            parsed.get("dimension_scores")
            or parsed.get("dimensions")
            or {}
        )
        return {
            "score": float(parsed.get("score", 0.0)),
            "reasoning": str(parsed.get("reasoning", "")),
            "dimension_scores": dims,
        }


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
