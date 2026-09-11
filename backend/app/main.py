"""AgentMate — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import api_router
from app.config import settings
from app.__init_db import engine, get_db
from app.auth.deps import get_current_space
from app.models import Base


def _seed_builtin_prompts(sync_conn):
    """Create built-in prompt templates for each evaluation strategy."""
    import json as _json
    from datetime import datetime
    from sqlalchemy import text as _sa_text

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _empty_json = _json.dumps([])
    builtins = [
        {
            "seq": 1, "id": "builtin_simple", "name": "通用评分（中文范例）", "description": "适用于通用质量评估的中文范例模板。可直接使用，或按需修改「评分维度」与「评分标准」适配自己的测试场景。",
            "strategy": "simple", "is_builtin": 1, "version": "1.0-zh",
            "system_prompt": (
                "你是一位资深的 AI 回复质量评估专家，负责对 AI 智能体的输出进行客观、严谨的打分。\n"
                "你的评分必须基于事实、逻辑清晰、标准一致——同样的回复在任何情况下都应得到相近的分数。\n"
                "评分范围严格限定在 0.0 到 1.0 之间。"
            ),
            "user_prompt_template": (
                "## 任务说明\n请评估 AI 智能体针对用户问题的回复质量，给出 0.0-1.0 的评分。\n\n"
                "## 用户输入\n{{input}}\n\n"
                "{% if expected_output %}\n## 参考答案\n以下是为该问题准备的参考答案，可作为评判质量的依据之一：\n{{expected_output}}\n{% endif %}\n\n"
                "{% if criteria %}\n## 评分准则\n请重点依据以下准则进行评判：\n{{criteria}}\n{% endif %}\n\n"
                "## 实际输出\n以下是被评估的 AI 智能体的实际回复：\n{{actual_output}}\n\n"
                "## 评分维度（供参考，可结合评分准则调整）\n请从以下维度综合考量：\n"
                "1. **准确性**：内容是否事实正确、无明显错误\n"
                "2. **完整性**：是否覆盖了问题的关键要点\n"
                "3. **相关性**：是否紧扣问题、无跑题\n"
                "4. **清晰度**：表达是否通顺、条理清晰\n\n"
                "## 评分标准\n"
                "- **0.9-1.0**：优秀，准确完整，无明显缺陷\n"
                "- **0.7-0.9**：良好，基本正确，有少量不足\n"
                "- **0.5-0.7**：一般，存在明显缺漏或部分错误\n"
                "- **0.3-0.5**：较差，有较多错误或信息缺失\n"
                "- **0.0-0.3**：很差，答非所问或严重错误\n\n"
                "## 扣分项\n出现以下情况时，应在对应维度上酌情扣分：\n"
                "- **事实性错误**：包含明显错误的事实、数据或结论，扣分从重\n"
                "- **答非所问**：未回应用户的真实问题或意图，大幅扣分\n"
                "- **信息缺失**：遗漏关键要点或必要信息，按缺失程度扣分\n"
                "- **逻辑混乱**：推理过程前后矛盾、条理不清，酌情扣分\n"
                "- **有害或不当内容**：包含不当、歧视性或有害表述，严重扣分\n"
                "- **格式错误**：未按要求的结构或格式输出，酌情扣分\n\n"
                "## 输出要求\n"
                "请先简要说明你的分析理由，再给出最终评分。必须严格按照以下 JSON 格式输出，不要包含其他内容：\n"
                '```json\n{"reasoning": "你的分析理由...", "score": 0.85}\n```'
            ),
            "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示综合质量评分", "reasoning": "string，说明评分的主要依据与分析过程"}, ensure_ascii=False),
            "output_format": "json", "template_content": "", "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria"]),
            "created_at": now, "updated_at": now,
        },
        {
            "seq": 2, "id": "builtin_reference", "name": "参照对比（中文范例）", "description": "将实际输出与参考答案进行对比评分的中文范例模板。未提供参考答案时自动降级为质量评估。",
            "strategy": "reference", "is_builtin": 1, "version": "1.0-zh",
            "system_prompt": (
                "你是一位资深的 AI 回复质量评估专家，负责将 AI 智能体的实际输出与参考答案进行严谨对比，并给出客观评分。\n"
                "你的评分必须基于事实与标准答案，逻辑清晰、标准一致——同样的对比结果在任何情况下都应得到相近的分数。\n"
                "评分范围严格限定在 0.0 到 1.0 之间。"
            ),
            "user_prompt_template": (
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
            ),
            "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示与参考答案的匹配程度", "reasoning": "string，包含命中/遗漏/偏差的对比分析", "dimensions": {"准确性": "number", "完整性": "number", "清晰度": "number"}}, ensure_ascii=False),
            "output_format": "json", "template_content": "", "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria"]),
            "created_at": now, "updated_at": now,
        },
        {
            "seq": 3, "id": "builtin_rubric", "name": "多维度评分（中文范例）", "description": "对 AI 输出进行多维度评估的中文范例模板。含评分规约时按规约逐维度打分，无规约时自动降级为默认 3 维度。",
            "strategy": "rubric", "is_builtin": 1, "version": "1.0-zh",
            "system_prompt": (
                "你是一位资深的 AI 回复质量评估专家，负责依据评分规约对 AI 智能体的输出进行多维度、客观的打分。\n"
                "你必须严格按照评分规约中定义的每个维度逐项评估，评分标准一致——同样的输出在任何情况下都应得到相近的分数。\n"
                "评分范围严格限定在 0.0 到 1.0 之间。"
            ),
            "user_prompt_template": (
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
            ),
            "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示加权总分", "reasoning": "string，包含各维度的分析理由", "dimensions": {"准确性": "number", "完整性": "number", "清晰度": "number"}}, ensure_ascii=False),
            "output_format": "json", "template_content": "", "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria", "rubric"]),
            "created_at": now, "updated_at": now,
        },
        {
            "seq": 4, "id": "builtin_cot", "name": "思维链评分（中文范例）", "description": "通过分步推理后再给出评分的中文范例模板。采用「先推理、后结论」的五步结构化分析。",
            "strategy": "chain_of_thought", "is_builtin": 1, "version": "1.0-zh",
            "system_prompt": (
                "你是一位资深的 AI 回复质量评估专家，擅长通过严谨的分步推理，对 AI 智能体的输出进行客观、可信的打分。\n"
                "你必须遵循「先推理、后结论」的原则：先按步骤逐条分析，再基于分析结果给出评分，保证评分的可解释性。\n"
                "评分范围严格限定在 0.0 到 1.0 之间。"
            ),
            "user_prompt_template": (
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
            ),
            "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示综合质量评分", "reasoning": "string，包含完整的5步推理分析过程"}, ensure_ascii=False),
            "output_format": "json", "template_content": "", "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria"]),
            "created_at": now, "updated_at": now,
        },
        {
            "seq": 5, "id": "builtin_fewshot", "name": "少样本评分（中文范例）", "description": "参考已标注的评分示例进行评分的中文范例模板。未提供示例时自动降级为通用质量评估。",
            "strategy": "few_shot", "is_builtin": 1, "version": "1.0-zh",
            "system_prompt": (
                "你是一位资深的 AI 回复质量评估专家，负责参考已给定的评分示例，对 AI 智能体的输出进行客观、严谨的打分。\n"
                "你必须保持与示例一致的评分标准与尺度——产出与示例相似的质量应得到相近的分数。\n"
                "评分范围严格限定在 0.0 到 1.0 之间。"
            ),
            "user_prompt_template": (
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
            ),
            "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示综合质量评分", "reasoning": "string，说明评分的主要依据，需与示例尺度保持一致"}, ensure_ascii=False),
            "output_format": "json", "template_content": "", "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria", "few_shot_examples"]),
            "few_shot_examples": _json.dumps([], ensure_ascii=False),
            "created_at": now, "updated_at": now,
        },
        {
            "seq": 6, "id": "builtin_pairwise", "name": "对比选择 (默认)", "description": "比较两个回复选择更好的",
            "strategy": "pairwise", "is_builtin": 1, "version": "1.0",
            "system_prompt": "You are an expert AI evaluation judge. Compare two AI responses and choose the better one.",
            "user_prompt_template": (
                "## Input\n{{input}}\n\n"
                "## Response A\n{{actual_output}}\n\n"
                "## Response B\n{{pairwise_alternative}}\n\n"
                "Analyze both responses and determine which is better.\n"
                "Provide your reasoning and a score for each response (0.0-1.0).\n"
                "## Output Format\n"
                '```json\n{"reasoning": "Comparative analysis...", '
                '"score": 0.85, '
                '"dimension_scores": {"response_a_score": 0.85, "response_b_score": 0.72, "preference": "A"}}\n```'
            ),
            "output_schema": _json.dumps({"score": "number 0-1", "reasoning": "string", "dimensions": {"response_a_score": "number", "response_b_score": "number", "preference": "string"}}),
            "output_format": "json", "template_content": "", "variables": _empty_json,
            "created_at": now, "updated_at": now,
        },
    ]

    for bp in builtins:
        cols = ", ".join(bp.keys())
        placeholders = ", ".join(f":{k}" for k in bp.keys())
        sync_conn.execute(
            _sa_text(f"INSERT OR IGNORE INTO eval_prompt_templates ({cols}) VALUES ({placeholders})"),
            bp,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables and run migrations on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Seed default admin user
        from app.auth.password import hash_password
        from datetime import datetime
        _empty_json = "[]"
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        def _seed_admin(sync_conn):
            from sqlalchemy import text as _sa_text
            admin = {
                "id": "admin",
                "username": "admin",
                "email": "admin@agentmate.local",
                "hashed_password": hash_password("admin123"),
                "role": "admin",
                "is_active": 1,
                "display_name": "System Administrator",
                "created_at": now,
                "updated_at": now,
            }
            cols = ", ".join(admin.keys())
            placeholders = ", ".join(f":{k}" for k in admin.keys())
            sync_conn.execute(
                _sa_text(f"INSERT OR IGNORE INTO users ({cols}) VALUES ({placeholders})"),
                admin,
            )
        await conn.run_sync(_seed_admin)
        # Migration: add description column to rules if missing
        from sqlalchemy import text
        from sqlalchemy import inspect
        def _migrate(sync_conn):
            inspector = inspect(sync_conn)
            table_names = inspector.get_table_names()

            # Add description column to rules
            if "rules" in table_names:
                columns = [c["name"] for c in inspector.get_columns("rules")]
                if "description" not in columns:
                    sync_conn.execute(text("ALTER TABLE rules ADD COLUMN description TEXT"))
                if "score_config_id" not in columns:
                    sync_conn.execute(text("ALTER TABLE rules ADD COLUMN score_config_id VARCHAR(36) REFERENCES score_configs(id)"))
                if "eval_strategy" not in columns:
                    sync_conn.execute(text("ALTER TABLE rules ADD COLUMN eval_strategy VARCHAR(20)"))

            # Create score_configs table if not present
            if "score_configs" not in table_names:
                sync_conn.execute(text("""
                    CREATE TABLE score_configs (
                        id VARCHAR(36) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        data_type VARCHAR(20) NOT NULL DEFAULT 'NUMERIC',
                        min_value FLOAT,
                        max_value FLOAT,
                        categories JSON,
                        "default" FLOAT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

            # Create annotations table if not present
            if "annotations" not in table_names:
                sync_conn.execute(text("""
                    CREATE TABLE annotations (
                        id VARCHAR(36) PRIMARY KEY,
                        task_result_id VARCHAR(36) NOT NULL REFERENCES task_results(id),
                        score FLOAT NOT NULL,
                        comment TEXT,
                        label VARCHAR(50),
                        annotator VARCHAR(255),
                        status VARCHAR(20) NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

            # Migrate ai_judge_models: add headers_template column
            if "ai_judge_models" in table_names:
                cols = [c["name"] for c in inspector.get_columns("ai_judge_models") if c["name"] in ("headers_template",)]
                if "headers_template" not in cols:
                    sync_conn.execute(text("ALTER TABLE ai_judge_models ADD COLUMN headers_template JSON"))

            # Migrate eval_prompt_templates: add new columns
            if "eval_prompt_templates" in table_names:
                columns = [c["name"] for c in inspector.get_columns("eval_prompt_templates")]
                if "strategy" not in columns:
                    sync_conn.execute(text("ALTER TABLE eval_prompt_templates ADD COLUMN strategy VARCHAR(20) NOT NULL DEFAULT 'simple'"))
                if "system_prompt" not in columns:
                    sync_conn.execute(text("ALTER TABLE eval_prompt_templates ADD COLUMN system_prompt TEXT"))
                if "user_prompt_template" not in columns:
                    sync_conn.execute(text("ALTER TABLE eval_prompt_templates ADD COLUMN user_prompt_template TEXT"))
                    # Migrate existing template_content -> user_prompt_template
                    sync_conn.execute(text("UPDATE eval_prompt_templates SET user_prompt_template = template_content WHERE user_prompt_template IS NULL AND template_content IS NOT NULL"))
                if "output_schema" not in columns:
                    sync_conn.execute(text("ALTER TABLE eval_prompt_templates ADD COLUMN output_schema JSON"))
                if "few_shot_examples" not in columns:
                    sync_conn.execute(text("ALTER TABLE eval_prompt_templates ADD COLUMN few_shot_examples JSON"))
                if "seq" not in columns:
                    sync_conn.execute(text("ALTER TABLE eval_prompt_templates ADD COLUMN seq INTEGER"))
                # Assign seq for existing built-in prompts
                seq_assign = sync_conn.execute(text("SELECT COUNT(*) FROM eval_prompt_templates WHERE seq IS NULL AND is_builtin = 1")).scalar()
                if seq_assign > 0:
                    sync_conn.execute(text("""
                        UPDATE eval_prompt_templates SET seq = CASE id
                            WHEN 'builtin_simple' THEN 1
                            WHEN 'builtin_reference' THEN 2
                            WHEN 'builtin_rubric' THEN 3
                            WHEN 'builtin_cot' THEN 4
                            WHEN 'builtin_fewshot' THEN 5
                            WHEN 'builtin_pairwise' THEN 6
                        END WHERE id IN ('builtin_simple','builtin_reference','builtin_rubric','builtin_cot','builtin_fewshot','builtin_pairwise')
                    """))
                # Assign seq for custom templates (101+)
                custom_count = sync_conn.execute(text("SELECT COUNT(*) FROM eval_prompt_templates WHERE seq IS NULL AND (is_builtin IS NULL OR is_builtin = 0)")).scalar()
                if custom_count > 0:
                    sync_conn.execute(text("""
                        UPDATE eval_prompt_templates SET seq = 100 + rowid
                        WHERE seq IS NULL AND (is_builtin IS NULL OR is_builtin = 0)
                    """))
                if "tags" not in columns:
                    sync_conn.execute(text("ALTER TABLE eval_prompt_templates ADD COLUMN tags JSON"))

                # Seed built-in prompt templates for each strategy if none exist
                count = sync_conn.execute(text("SELECT COUNT(*) FROM eval_prompt_templates WHERE is_builtin = 1")).scalar()
                if count == 0:
                    _seed_builtin_prompts(sync_conn)
                else:
                    # Force-refresh the builtin_simple template to the latest Chinese example
                    # (INSERT OR IGNORE in _seed_builtin_prompts never updates existing rows).
                    import json as _json
                    _seed_builtin_prompts(sync_conn)
                    sync_conn.execute(text("""
                        UPDATE eval_prompt_templates SET
                            name = :name,
                            description = :description,
                            system_prompt = :system_prompt,
                            user_prompt_template = :user_prompt_template,
                            output_schema = :output_schema,
                            variables = :variables,
                            version = '1.0-zh'
                        WHERE id = 'builtin_simple'
                          AND is_builtin = 1
                          AND version != '1.0-zh'
                    """), {
                        "name": "通用评分（中文范例）",
                        "description": "适用于通用质量评估的中文范例模板。可直接使用，或按需修改「评分维度」与「评分标准」适配自己的测试场景。",
                        "system_prompt": (
                            "你是一位资深的 AI 回复质量评估专家，负责对 AI 智能体的输出进行客观、严谨的打分。\n"
                            "你的评分必须基于事实、逻辑清晰、标准一致——同样的回复在任何情况下都应得到相近的分数。\n"
                            "评分范围严格限定在 0.0 到 1.0 之间。"
                        ),
                        "user_prompt_template": (
                            "## 任务说明\n请评估 AI 智能体针对用户问题的回复质量，给出 0.0-1.0 的评分。\n\n"
                            "## 用户输入\n{{input}}\n\n"
                            "{% if expected_output %}\n## 参考答案\n以下是为该问题准备的参考答案，可作为评判质量的依据之一：\n{{expected_output}}\n{% endif %}\n\n"
                            "{% if criteria %}\n## 评分准则\n请重点依据以下准则进行评判：\n{{criteria}}\n{% endif %}\n\n"
                            "## 实际输出\n以下是被评估的 AI 智能体的实际回复：\n{{actual_output}}\n\n"
                            "## 评分维度（供参考，可结合评分准则调整）\n请从以下维度综合考量：\n"
                            "1. **准确性**：内容是否事实正确、无明显错误\n"
                            "2. **完整性**：是否覆盖了问题的关键要点\n"
                            "3. **相关性**：是否紧扣问题、无跑题\n"
                            "4. **清晰度**：表达是否通顺、条理清晰\n\n"
                            "## 评分标准\n"
                            "- **0.9-1.0**：优秀，准确完整，无明显缺陷\n"
                            "- **0.7-0.9**：良好，基本正确，有少量不足\n"
                            "- **0.5-0.7**：一般，存在明显缺漏或部分错误\n"
                            "- **0.3-0.5**：较差，有较多错误或信息缺失\n"
                            "- **0.0-0.3**：很差，答非所问或严重错误\n\n"
                            "## 扣分项\n出现以下情况时，应在对应维度上酌情扣分：\n"
                            "- **事实性错误**：包含明显错误的事实、数据或结论，扣分从重\n"
                            "- **答非所问**：未回应用户的真实问题或意图，大幅扣分\n"
                            "- **信息缺失**：遗漏关键要点或必要信息，按缺失程度扣分\n"
                            "- **逻辑混乱**：推理过程前后矛盾、条理不清，酌情扣分\n"
                            "- **有害或不当内容**：包含不当、歧视性或有害表述，严重扣分\n"
                            "- **格式错误**：未按要求的结构或格式输出，酌情扣分\n\n"
                            "## 输出要求\n"
                            "请先简要说明你的分析理由，再给出最终评分。必须严格按照以下 JSON 格式输出，不要包含其他内容：\n"
                            '```json\n{"reasoning": "你的分析理由...", "score": 0.85}\n```'
                        ),
                        "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示综合质量评分", "reasoning": "string，说明评分的主要依据与分析过程"}, ensure_ascii=False),
                        "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria"]),
                    })
                    # Force-refresh the builtin_reference template to the latest Chinese example
                    sync_conn.execute(text("""
                        UPDATE eval_prompt_templates SET
                            name = :name,
                            description = :description,
                            system_prompt = :system_prompt,
                            user_prompt_template = :user_prompt_template,
                            output_schema = :output_schema,
                            variables = :variables,
                            version = '1.0-zh'
                        WHERE id = 'builtin_reference'
                          AND is_builtin = 1
                          AND version != '1.0-zh'
                    """), {
                        "name": "参照对比（中文范例）",
                        "description": "将实际输出与参考答案进行对比评分的中文范例模板。未提供参考答案时自动降级为质量评估。",
                        "system_prompt": (
                            "你是一位资深的 AI 回复质量评估专家，负责将 AI 智能体的实际输出与参考答案进行严谨对比，并给出客观评分。\n"
                            "你的评分必须基于事实与标准答案，逻辑清晰、标准一致——同样的对比结果在任何情况下都应得到相近的分数。\n"
                            "评分范围严格限定在 0.0 到 1.0 之间。"
                        ),
                        "user_prompt_template": (
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
                        ),
                        "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示与参考答案的匹配程度", "reasoning": "string，包含命中/遗漏/偏差的对比分析", "dimensions": {"准确性": "number", "完整性": "number", "清晰度": "number"}}, ensure_ascii=False),
                        "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria"]),
                    })
                    # Force-refresh the builtin_rubric template to the latest Chinese example
                    sync_conn.execute(text("""
                        UPDATE eval_prompt_templates SET
                            name = :name,
                            description = :description,
                            system_prompt = :system_prompt,
                            user_prompt_template = :user_prompt_template,
                            output_schema = :output_schema,
                            variables = :variables,
                            version = '1.0-zh'
                        WHERE id = 'builtin_rubric'
                          AND is_builtin = 1
                          AND version != '1.0-zh'
                    """), {
                        "name": "多维度评分（中文范例）",
                        "description": "对 AI 输出进行多维度评估的中文范例模板。含评分规约时按规约逐维度打分，无规约时自动降级为默认 3 维度。",
                        "system_prompt": (
                            "你是一位资深的 AI 回复质量评估专家，负责依据评分规约对 AI 智能体的输出进行多维度、客观的打分。\n"
                            "你必须严格按照评分规约中定义的每个维度逐项评估，评分标准一致——同样的输出在任何情况下都应得到相近的分数。\n"
                            "评分范围严格限定在 0.0 到 1.0 之间。"
                        ),
                        "user_prompt_template": (
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
                        ),
                        "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示加权总分", "reasoning": "string，包含各维度的分析理由", "dimensions": {"准确性": "number", "完整性": "number", "清晰度": "number"}}, ensure_ascii=False),
                        "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria", "rubric"]),
                    })
                    # Force-refresh the builtin_fewshot template to the latest Chinese example
                    sync_conn.execute(text("""
                        UPDATE eval_prompt_templates SET
                            name = :name,
                            description = :description,
                            system_prompt = :system_prompt,
                            user_prompt_template = :user_prompt_template,
                            output_schema = :output_schema,
                            variables = :variables,
                            version = '1.0-zh'
                        WHERE id = 'builtin_fewshot'
                          AND is_builtin = 1
                          AND version != '1.0-zh'
                    """), {
                        "name": "少样本评分（中文范例）",
                        "description": "参考已标注的评分示例进行评分的中文范例模板。未提供示例时自动降级为通用质量评估。",
                        "system_prompt": (
                            "你是一位资深的 AI 回复质量评估专家，负责参考已给定的评分示例，对 AI 智能体的输出进行客观、严谨的打分。\n"
                            "你必须保持与示例一致的评分标准与尺度——产出与示例相似的质量应得到相近的分数。\n"
                            "评分范围严格限定在 0.0 到 1.0 之间。"
                        ),
                        "user_prompt_template": (
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
                        ),
                        "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示综合质量评分", "reasoning": "string，说明评分的主要依据，需与示例尺度保持一致"}, ensure_ascii=False),
                        "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria", "few_shot_examples"]),
                    })
                    # Force-refresh the builtin_cot template to the latest Chinese example
                    sync_conn.execute(text("""
                        UPDATE eval_prompt_templates SET
                            name = :name,
                            description = :description,
                            system_prompt = :system_prompt,
                            user_prompt_template = :user_prompt_template,
                            output_schema = :output_schema,
                            variables = :variables,
                            version = '1.0-zh'
                        WHERE id = 'builtin_cot'
                          AND is_builtin = 1
                          AND version != '1.0-zh'
                    """), {
                        "name": "思维链评分（中文范例）",
                        "description": "通过分步推理后再给出评分的中文范例模板。采用「先推理、后结论」的五步结构化分析。",
                        "system_prompt": (
                            "你是一位资深的 AI 回复质量评估专家，擅长通过严谨的分步推理，对 AI 智能体的输出进行客观、可信的打分。\n"
                            "你必须遵循「先推理、后结论」的原则：先按步骤逐条分析，再基于分析结果给出评分，保证评分的可解释性。\n"
                            "评分范围严格限定在 0.0 到 1.0 之间。"
                        ),
                        "user_prompt_template": (
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
                        ),
                        "output_schema": _json.dumps({"score": "number 0-1 的浮点数，表示综合质量评分", "reasoning": "string，包含完整的5步推理分析过程"}, ensure_ascii=False),
                        "variables": _json.dumps(["input", "actual_output", "expected_output", "criteria"]),
                    })

            # Auto-create default ScoreConfigs for all three scoring types
            if "score_configs" in table_names:
                count = sync_conn.execute(text("SELECT COUNT(*) FROM score_configs")).scalar()
                if count == 0:
                    sync_conn.execute(text("""
                        INSERT INTO score_configs (id, name, description, data_type, min_value, max_value)
                        VALUES ('default_numeric', '默认数值评分', '数值评分 0.0~1.0', 'NUMERIC', 0.0, 1.0)
                    """))
                    sync_conn.execute(text("""
                        INSERT INTO score_configs (id, name, description, data_type, min_value, max_value)
                        VALUES ('default_boolean', '默认布尔评分', '布尔评分 通过/不通过', 'BOOLEAN', 0.0, 1.0)
                    """))
                    sync_conn.execute(text("""
                        INSERT INTO score_configs (id, name, description, data_type)
                        VALUES ('default_categorical', '默认分类评分', '分类评分 优/良/中/差', 'CATEGORICAL')
                    """))
                    # Link existing rules to default ScoreConfig
                    if "rules" in table_names:
                        sync_conn.execute(text("UPDATE rules SET score_config_id = 'default_numeric' WHERE score_config_id IS NULL"))

            # Migration: add display_id column to tasks
            if "tasks" in table_names:
                cols = [c["name"] for c in inspector.get_columns("tasks")]
                if "display_id" not in cols:
                    sync_conn.execute(text("ALTER TABLE tasks ADD COLUMN display_id VARCHAR(6)"))
                    # Assign display_id for existing tasks (natural order by created_at)
                    existing_tasks = sync_conn.execute(
                        text("SELECT id, ROW_NUMBER() OVER (ORDER BY created_at) AS rn FROM tasks")
                    ).fetchall()
                    for row in existing_tasks:
                        display_id = str(row.rn).zfill(6)
                        sync_conn.execute(
                            text("UPDATE tasks SET display_id = :did WHERE id = :tid"),
                            {"did": display_id, "tid": row.id},
                        )
                    # Add unique constraint
                    sync_conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_tasks_display_id ON tasks(display_id)"))
        # Migration: create default space + add space_id to all entity tables
        def _migrate_space(sync_conn):
            inspector = inspect(sync_conn)
            table_names = inspector.get_table_names()

            # Create spaces table if missing (safety net — create_all should handle it)
            if "spaces" not in table_names:
                sync_conn.execute(text("""
                    CREATE TABLE spaces (
                        id VARCHAR(36) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        owner_id VARCHAR(36) NOT NULL REFERENCES users(id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

            # Ensure owner_id index on spaces
            if "spaces" in table_names:
                try:
                    sync_conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_spaces_owner_id ON spaces(owner_id)"))
                except Exception:
                    pass  # index may already exist

            # Tables that need space_id column
            space_id_tables = [
                "agents", "datasets", "test_cases", "rules", "score_configs",
                "objectives", "ai_judge_models", "eval_prompt_templates",
                "scoring_rubrics", "tasks", "task_results", "annotations",
                "category_weights", "objective_weights",
            ]
            for tbl in space_id_tables:
                if tbl in table_names:
                    cols = [c["name"] for c in inspector.get_columns(tbl)]
                    if "space_id" not in cols:
                        sync_conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN space_id VARCHAR(36) REFERENCES spaces(id)"))

            # Create default space for admin user
            admin_exists = sync_conn.execute(text("SELECT COUNT(*) FROM users WHERE id = 'admin'")).scalar() > 0
            if admin_exists:
                space_exists = sync_conn.execute(text("SELECT COUNT(*) FROM spaces WHERE id = 'space_default'")).scalar() > 0
                if not space_exists:
                    from datetime import datetime
                    _now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    sync_conn.execute(text("""
                        INSERT INTO spaces (id, name, description, owner_id, created_at, updated_at)
                        VALUES ('space_default', 'Default Space', 'Default admin space', 'admin', :now, :now)
                    """), {"now": _now})

                # Assign existing non-builtin data to default space
                tables_with_builtin = {
                    "eval_prompt_templates": "is_builtin",
                    "score_configs": None,  # no is_builtin, check default_numeric specially
                }
                for tbl in space_id_tables:
                    if tbl in table_names:
                        cols = [c["name"] for c in inspector.get_columns(tbl)]
                        if "space_id" in cols:
                            has_is_builtin = "is_builtin" in cols
                            if has_is_builtin and tbl in tables_with_builtin:
                                # Only update non-builtin rows
                                sync_conn.execute(text(
                                    f"UPDATE {tbl} SET space_id = 'space_default' WHERE space_id IS NULL AND is_builtin = 0"
                                ))
                            elif has_is_builtin:
                                sync_conn.execute(text(
                                    f"UPDATE {tbl} SET space_id = 'space_default' WHERE space_id IS NULL AND is_builtin = 0"
                                ))
                            else:
                                # No is_builtin flag — assign all to default space
                                # Skip default_numeric for score_configs
                                if tbl == "score_configs":
                                    sync_conn.execute(text(
                                        "UPDATE score_configs SET space_id = 'space_default' WHERE space_id IS NULL AND id != 'default_numeric'"
                                    ))
                                else:
                                    sync_conn.execute(text(
                                        f"UPDATE {tbl} SET space_id = 'space_default' WHERE space_id IS NULL"
                                    ))

        await conn.run_sync(_migrate_space)
        await conn.run_sync(_migrate)

    # Log production security warning
    import logging as _logging
    _log = _logging.getLogger("agentmate")
    _log.info("Database: %s", settings.database_url)

    # Set database file permissions to 600 (owner read/write only)
    # This is effective on Linux/macOS; ignored on Windows.
    try:
        _db_path = settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if _db_path:
            import os as _os
            _os.chmod(_db_path, 0o600)
            _log.info("Database file permissions set to 600")
    except Exception:
        pass  # Windows or permission error — silently skip

    # Warn if database is under project directory (production safety)
    if "./data/" in str(settings.database_url):
        _log.warning(
            "Database is stored under the project directory (./data/). "
            "For production, set TESTHUB_DATABASE_URL to a path outside the "
            "web root, e.g. /var/lib/agentmate/data/agentmate.db"
        )

    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.app_version, "app": settings.app_name}


@app.get("/api/v1/dashboard/stats")
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_space: str | None = Depends(get_current_space),
):
    """Dashboard statistics endpoint."""
    from app import repositories as repo

    tasks = await repo.list_tasks(db, space_id=current_space, limit=100)
    total_tasks = len(tasks)
    completed = sum(1 for t in tasks if t.status == "completed")
    running = sum(1 for t in tasks if t.status == "running")

    agents = await repo.list_agents(db, space_id=current_space)
    judges = await repo.list_ai_judges(db, space_id=current_space)
    datasets = await repo.list_datasets(db, space_id=current_space)

    return {
            "total_tasks": total_tasks,
            "completed_tasks": completed,
            "running_tasks": running,
            "total_agents": len(agents),
            "total_judges": len(judges),
            "total_datasets": len(datasets),
            "recent_tasks": [
                {"id": t.id, "name": t.name, "status": t.status, "created_at": str(t.created_at)}
                for t in tasks[:10]
            ],
        }


def run():
    """Entry point for 'agentmate serve'."""
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)


if __name__ == "__main__":
    run()
