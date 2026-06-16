"""AI Judge Module — multi-provider LLM-as-a-judge evaluation."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any

import httpx
from jinja2 import Template, StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

logger = logging.getLogger("agentmate.judge")

# Ensure log file handler is set up once
if not logger.handlers:
    from app.config import settings
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    fh = logging.FileHandler(str(settings.data_path / "logs" / "judge.log"), encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)


# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class JudgeResponse:
    score: float = 0.0
    reasoning: str = ""
    dimension_scores: dict[str, float] | None = None
    raw_response: str | None = None
    error: str | None = None
    model_name: str = ""
    latency_ms: float = 0.0


@dataclass
class ArbitrationResult:
    final_score: float = 0.0
    strategy: str = "avg"
    individual_scores: list[float] = field(default_factory=list)
    variance: float = 0.0
    num_judges: int = 0
    warnings: list[str] = field(default_factory=list)

    def dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PromptContext:
    input: str = ""
    expected_output: str = ""
    actual_output: str = ""
    rubric: str = ""
    criteria: str = ""
    pairwise_alternative: str = ""
    few_shot_examples: list = field(default_factory=list)
    output_schema: dict = field(default_factory=dict)


# ── Prompt Renderer ──────────────────────────────────────────────────────

class PromptRenderer:
    """Renders Jinja2 prompt templates with sandboxed environment."""

    _env = SandboxedEnvironment(undefined=StrictUndefined)

    def render(self, template: str, ctx: PromptContext) -> str:
        try:
            tpl = self._env.from_string(template)
            return tpl.render(**asdict(ctx))
        except TemplateError as e:
            logger.warning("Prompt rendering failed: %s", e)
            # Re-raise so the caller can handle it; never fall back to unsafe mode
            raise


# ── Model Adapters ───────────────────────────────────────────────────────

class ModelAdapter(ABC):
    """Base adapter for AI judge model providers."""

    @abstractmethod
    async def invoke(self, model_cfg: dict, prompt: str, params: dict) -> JudgeResponse:
        ...


class OpenAIAdapter(ModelAdapter):
    """OpenAI-compatible API adapter."""

    async def invoke(self, model_cfg: dict, prompt: str, params: dict) -> JudgeResponse:
        import time
        start = time.monotonic()
        api_key = model_cfg.get("auth_credentials", "")
        base_url = model_cfg.get("api_base_url", "https://api.openai.com/v1").rstrip("/")
        model_name = model_cfg.get("model_name", "gpt-4o")

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": params.get("temperature", 0.0),
            "max_tokens": params.get("max_tokens", 2048),
        }

        try:
            safe_headers = {"Authorization": "Bearer " + api_key[:10] + "…"} if api_key else {}
            logger.info("─" * 60)
            logger.info("[JUDGE] >>> REQUEST  POST  %s/chat/completions", base_url)
            logger.info("[JUDGE] >>> Headers: %s", json.dumps(safe_headers, ensure_ascii=False))
            logger.info("[JUDGE] >>> Model:   %s", model_name)
            logger.info("[JUDGE] >>> Prompt:  %s", prompt[:300])
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{base_url}/chat/completions", json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            latency = (time.monotonic() - start) * 1000
            logger.info("[JUDGE] <<< RESPONSE [%s] (%dms) score=… raw=%.200s", resp.status_code, latency, raw)
            return _parse_judge_response(raw, model_name, latency)
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.warning("[JUDGE] <<< ERROR  %s", e)
            return JudgeResponse(error=str(e), raw_response=str(e), model_name=model_name, latency_ms=latency)


class AnthropicAdapter(ModelAdapter):
    """Anthropic API adapter."""

    async def invoke(self, model_cfg: dict, prompt: str, params: dict) -> JudgeResponse:
        import time
        start = time.monotonic()
        api_key = model_cfg.get("auth_credentials", "")
        base_url = model_cfg.get("api_base_url", "https://api.anthropic.com").rstrip("/")
        model_name = model_cfg.get("model_name", "claude-sonnet-4-20250514")

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": model_name,
            "max_tokens": params.get("max_tokens", 2048),
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            safe_headers = {"x-api-key": api_key[:10] + "…"} if api_key else {}
            logger.info("─" * 60)
            logger.info("[JUDGE] >>> REQUEST  POST  %s/v1/messages", base_url)
            logger.info("[JUDGE] >>> Headers: %s", json.dumps(safe_headers, ensure_ascii=False))
            logger.info("[JUDGE] >>> Model:   %s", model_name)
            logger.info("[JUDGE] >>> Prompt:  %s", prompt[:300])
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{base_url}/v1/messages", json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            raw = data["content"][0]["text"]
            latency = (time.monotonic() - start) * 1000
            logger.info("[JUDGE] <<< RESPONSE [%s] (%dms) raw=%.200s", resp.status_code, latency, raw)
            return _parse_judge_response(raw, model_name, latency)
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.warning("[JUDGE] <<< ERROR  %s", e)
            return JudgeResponse(error=str(e), raw_response=str(e), model_name=model_name, latency_ms=latency)


class CustomOpenAIAdapter(ModelAdapter):
    """Custom OpenAI-compatible adapter (same as OpenAI adapter)."""

    async def invoke(self, model_cfg: dict, prompt: str, params: dict) -> JudgeResponse:
        adapter = OpenAIAdapter()
        return await adapter.invoke(model_cfg, prompt, params)


# ── Response Parser ──────────────────────────────────────────────────────

def _parse_judge_response(raw: str, model_name: str = "", latency_ms: float = 0.0) -> JudgeResponse:
    """Four-layer fallback parser for AI judge responses."""

    result = JudgeResponse(raw_response=raw, model_name=model_name, latency_ms=latency_ms)

    # Layer 1: strict JSON parse
    try:
        data = json.loads(raw)
        result.score = float(data.get("score", 0.0))
        result.reasoning = data.get("reasoning", "") or data.get("explanation", "")
        result.dimension_scores = data.get("dimension_scores") or data.get("dimensions")
        return result
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Layer 2: extract JSON from markdown code block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            result.score = float(data.get("score", 0.0))
            result.reasoning = data.get("reasoning", "") or data.get("explanation", "")
            result.dimension_scores = data.get("dimension_scores") or data.get("dimensions")
            return result
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # Layer 3: regex extraction
    score_m = re.search(r'(?:score|rating):\s*([0-9]*\.?[0-9]+)', raw, re.I)
    reasoning_m = re.search(r'(?:reasoning|analysis|explanation):\s*(.+?)(?:\n|$)', raw, re.I | re.DOTALL)
    if score_m:
        try:
            result.score = float(score_m.group(1))
            result.reasoning = reasoning_m.group(1).strip() if reasoning_m else raw[:500]
            return result
        except (ValueError, TypeError):
            pass

    # Layer 4: default fallback
    result.score = 0.0
    result.reasoning = raw[:500] if raw else "No response from judge model"
    return result


# ── Model Router ─────────────────────────────────────────────────────────

class ModelRouter:
    """Routes AI judge requests to the appropriate provider adapter."""

    _adapters: dict[str, type[ModelAdapter]] = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
        "google": OpenAIAdapter,
        "azure": OpenAIAdapter,
        "custom": CustomOpenAIAdapter,
    }

    def invoke(self, model_cfg: dict, prompt: str, params: dict | None = None) -> JudgeResponse:
        provider = model_cfg.get("provider", "openai")
        adapter_cls = self._adapters.get(provider, OpenAIAdapter)
        adapter = adapter_cls()
        return adapter.invoke(model_cfg, prompt, params or {})


# ── Arbitration Engine ───────────────────────────────────────────────────

class ArbitrationEngine:
    """Arbitrates between multiple judge results."""

    STRATEGIES = ("avg", "min", "max", "weighted")

    async def arbitrate(
        self,
        results: list[JudgeResponse],
        strategy: str = "avg",
        weights: list[float] | None = None,
    ) -> ArbitrationResult:
        if not results:
            return ArbitrationResult(strategy=strategy, warnings=["No judge results provided"])

        valid = [r for r in results if r.error is None and r.score is not None]
        if not valid:
            return ArbitrationResult(strategy=strategy, warnings=["No valid judge results"])

        scores = [r.score for r in valid]
        n = len(scores)
        mean = sum(scores) / n
        variance = sum((s - mean) ** 2 for s in scores) / n if n > 1 else 0.0

        warnings = []
        if variance > 0.1:
            warnings.append(f"High variance ({variance:.4f}) among judges")

        if strategy == "min":
            final_score = min(scores)
        elif strategy == "max":
            final_score = max(scores)
        elif strategy == "weighted":
            w = weights or [1.0 / n] * n
            if len(w) != n:
                w = [1.0 / n] * n
            final_score = sum(s * w[i] for i, s in enumerate(scores))
        else:
            final_score = mean

        return ArbitrationResult(
            final_score=final_score,
            strategy=strategy,
            individual_scores=scores,
            variance=variance,
            num_judges=n,
            warnings=warnings,
        )


# ── Token Cost Estimator ─────────────────────────────────────────────────

class TokenCostEstimator:
    """Estimates token usage and cost for AI judge calls."""

    RATES: dict[str, tuple[float, float]] = {
        "gpt-4o": (2.50 / 1_000_000, 10.00 / 1_000_000),
        "gpt-4o-mini": (0.15 / 1_000_000, 0.60 / 1_000_000),
        "claude-sonnet-4-20250514": (3.00 / 1_000_000, 15.00 / 1_000_000),
        "claude-haiku-3-5": (1.00 / 1_000_000, 5.00 / 1_000_000),
        "DEFAULT": (1.00 / 1_000_000, 5.00 / 1_000_000),
    }

    @staticmethod
    def estimate_cost(text: str, model: str, is_output: bool = False) -> float:
        tokens = len(text) // 4 + 1
        rate = TokenCostEstimator.RATES.get(model, TokenCostEstimator.RATES["DEFAULT"])
        cost_per_token = rate[1] if is_output else rate[0]
        return tokens * cost_per_token

    @staticmethod
    def estimate_prompt_cost(prompt: str, model: str) -> float:
        return TokenCostEstimator.estimate_cost(prompt, model, is_output=False)

    @staticmethod
    def estimate_response_cost(response: str, model: str) -> float:
        return TokenCostEstimator.estimate_cost(response, model, is_output=True)
