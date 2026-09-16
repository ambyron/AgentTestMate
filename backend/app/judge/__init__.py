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

from app.config import settings

logger = logging.getLogger("agentmate.judge")

# Ensure log file handler is set up once
if not logger.handlers:
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
    # ── Structured failure info ─────────────────────────────────────────
    error_kind: str | None = None   # one of ERROR_* constants
    retryable: bool = False         # whether the caller should retry
    attempts: int = 1               # number of actual invocations


# ── Error Classification ─────────────────────────────────────────────────
#
# Judge calls can fail for many reasons; only a subset are worth retrying.
# Every failure is normalized into one of these kinds so that the scorer,
# the aggregator and the UI can all reason about it consistently.

ERROR_TIMEOUT = "timeout"              # connect/read timeout, or hard deadline
ERROR_CONNECTION = "connection"        # DNS / TCP / TLS failure
ERROR_RATE_LIMIT = "rate_limit"        # HTTP 429
ERROR_SERVER = "server_error"          # HTTP 5xx
ERROR_AUTH = "auth_error"              # HTTP 401 / 403 — retrying is pointless
ERROR_BAD_REQUEST = "bad_request"      # HTTP 4xx (other) — request itself is wrong
ERROR_PARSE = "parse_error"            # response received but JSON parsing failed
ERROR_EMPTY = "empty_response"         # response received but content is empty
ERROR_UNKNOWN = "unknown"

#: Error kinds for which a retry has a realistic chance of succeeding.
RETRYABLE_ERROR_KINDS = frozenset({
    ERROR_TIMEOUT,
    ERROR_CONNECTION,
    ERROR_RATE_LIMIT,
    ERROR_SERVER,
})

#: HTTP status code → error kind
_STATUS_TO_KIND = {
    400: ERROR_BAD_REQUEST,
    401: ERROR_AUTH,
    403: ERROR_AUTH,
    404: ERROR_BAD_REQUEST,
    408: ERROR_TIMEOUT,
    422: ERROR_BAD_REQUEST,
    429: ERROR_RATE_LIMIT,
}


def classify_error(exc: BaseException) -> str:
    """Normalize an exception raised by an HTTP call into an ERROR_* kind."""
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return ERROR_TIMEOUT
    if isinstance(exc, (httpx.ConnectError, httpx.RemoteProtocolError,
                        httpx.NetworkError, httpx.ProxyError)):
        return ERROR_CONNECTION
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else 0
        if status in _STATUS_TO_KIND:
            return _STATUS_TO_KIND[status]
        if 500 <= status < 600:
            return ERROR_SERVER
        if 400 <= status < 500:
            return ERROR_BAD_REQUEST
        return ERROR_UNKNOWN
    if isinstance(exc, httpx.HTTPError):
        return ERROR_CONNECTION
    return ERROR_UNKNOWN


def _classify_text_error(message: str) -> str:
    """Best-effort classification for non-exception error strings."""
    low = (message or "").lower()
    if "timeout" in low or "timed out" in low:
        return ERROR_TIMEOUT
    if "connection" in low or "connect" in low or "refused" in low:
        return ERROR_CONNECTION
    if "429" in low or "rate limit" in low:
        return ERROR_RATE_LIMIT
    if any(code in low for code in ("500", "502", "503", "504")):
        return ERROR_SERVER
    if "401" in low or "403" in low or "unauthorized" in low or "forbidden" in low:
        return ERROR_AUTH
    return ERROR_UNKNOWN


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
    async def invoke(self, model_cfg: dict, prompt: str, params: dict,
                     system_prompt: str | None = None) -> JudgeResponse:
        ...

    @staticmethod
    def _build_messages(prompt: str, system_prompt: str | None) -> list[dict]:
        """Build a standard messages list with optional system role."""
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _resolve_timeout(params: dict) -> float:
        """Resolve the per-request read timeout in seconds.

        Priority: params["timeout_ms"] > settings.ai_judge_scoring_timeout_ms.
        """
        raw = params.get("timeout_ms")
        if raw is None:
            raw = params.get("timeout_seconds")
            if raw is not None:
                return float(raw)
            return settings.ai_judge_scoring_timeout_ms / 1000.0
        try:
            ms = float(raw)
        except (TypeError, ValueError):
            return settings.ai_judge_scoring_timeout_ms / 1000.0
        if ms <= 0:
            return settings.ai_judge_scoring_timeout_ms / 1000.0
        return ms / 1000.0

    @staticmethod
    def _build_timeout(read_seconds: float) -> httpx.Timeout:
        """Per-stage timeout: connect/write/pool are short, read is configurable."""
        return httpx.Timeout(
            connect=5.0,
            read=read_seconds,
            write=10.0,
            pool=5.0,
        )

    @staticmethod
    def _failure(exc: BaseException, start: float, model_name: str) -> JudgeResponse:
        """Build a JudgeResponse describing a failed invocation."""
        import time
        kind = classify_error(exc) if isinstance(exc, Exception) else ERROR_UNKNOWN
        latency = (time.monotonic() - start) * 1000
        logger.warning("[JUDGE] <<< ERROR [%s] %s", kind, exc)
        return JudgeResponse(
            error=str(exc),
            error_kind=kind,
            retryable=kind in RETRYABLE_ERROR_KINDS,
            raw_response=str(exc),
            model_name=model_name,
            latency_ms=latency,
        )


class OpenAIAdapter(ModelAdapter):
    """OpenAI-compatible API adapter."""

    async def invoke(self, model_cfg: dict, prompt: str, params: dict,
                     system_prompt: str | None = None) -> JudgeResponse:
        import time
        start = time.monotonic()
        api_key = model_cfg.get("auth_credentials") or ""
        base_url = (model_cfg.get("api_base_url") or "https://api.openai.com/v1").rstrip("/")
        model_name = model_cfg.get("model_name") or "gpt-4o"

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        extra_headers = model_cfg.get("headers_template") or {}
        if isinstance(extra_headers, dict) and extra_headers:
            headers.update({str(k): str(v) for k, v in extra_headers.items()})
        body = {
            "model": model_name,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": params.get("temperature", 0.0),
            "max_tokens": params.get("max_tokens", settings.ai_judge_default_max_tokens),
        }

        read_timeout = self._resolve_timeout(params)
        try:
            safe_headers = {"Authorization": "Bearer " + api_key[:10] + "…"} if api_key else {}
            logger.info("─" * 60)
            logger.info("[JUDGE] >>> REQUEST  POST  %s/chat/completions", base_url)
            logger.info("[JUDGE] >>> Headers: %s", json.dumps(safe_headers, ensure_ascii=False))
            logger.info("[JUDGE] >>> Model:   %s  timeout=%.1fs", model_name, read_timeout)
            logger.info("[JUDGE] >>> Prompt:  %s", prompt[:300])
            client = _get_shared_client()
            resp = await client.post(
                f"{base_url}/chat/completions", json=body, headers=headers,
                timeout=self._build_timeout(read_timeout),
            )
            resp.raise_for_status()
            data = resp.json()
            # Safely extract content: handle missing/null choices/message/content
            raw = None
            try:
                raw = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                raw = str(data)
            if raw is None:
                raw = str(data)
            latency = (time.monotonic() - start) * 1000
            logger.info("[JUDGE] <<< RESPONSE [%s] (%dms) raw=%.200s", resp.status_code, latency, raw)
            return _parse_judge_response(raw, model_name, latency)
        except Exception as e:
            return self._failure(e, start, model_name)


class AnthropicAdapter(ModelAdapter):
    """Anthropic API adapter."""

    async def invoke(self, model_cfg: dict, prompt: str, params: dict,
                     system_prompt: str | None = None) -> JudgeResponse:
        import time
        start = time.monotonic()
        api_key = model_cfg.get("auth_credentials") or ""
        base_url = (model_cfg.get("api_base_url") or "https://api.anthropic.com").rstrip("/")
        model_name = model_cfg.get("model_name") or "claude-sonnet-4-20250514"

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": model_name,
            "max_tokens": params.get("max_tokens", settings.ai_judge_default_max_tokens),
            "messages": [{"role": "user", "content": prompt}],
        }
        # Anthropic uses a top-level system parameter
        if system_prompt:
            body["system"] = system_prompt

        read_timeout = self._resolve_timeout(params)
        try:
            safe_headers = {"x-api-key": api_key[:10] + "…"} if api_key else {}
            logger.info("─" * 60)
            logger.info("[JUDGE] >>> REQUEST  POST  %s/v1/messages", base_url)
            logger.info("[JUDGE] >>> Headers: %s", json.dumps(safe_headers, ensure_ascii=False))
            logger.info("[JUDGE] >>> Model:   %s  timeout=%.1fs", model_name, read_timeout)
            logger.info("[JUDGE] >>> Prompt:  %s", prompt[:300])
            client = _get_shared_client()
            resp = await client.post(
                f"{base_url}/v1/messages", json=body, headers=headers,
                timeout=self._build_timeout(read_timeout),
            )
            resp.raise_for_status()
            data = resp.json()
            # Safely extract content: handle missing/null content fields
            raw = None
            try:
                raw = data["content"][0]["text"]
            except (KeyError, IndexError, TypeError):
                raw = str(data)
            if raw is None:
                raw = str(data)
            latency = (time.monotonic() - start) * 1000
            logger.info("[JUDGE] <<< RESPONSE [%s] (%dms) raw=%.200s", resp.status_code, latency, raw)
            return _parse_judge_response(raw, model_name, latency)
        except Exception as e:
            return self._failure(e, start, model_name)


class CustomOpenAIAdapter(ModelAdapter):
    """Custom OpenAI-compatible adapter (same as OpenAI adapter)."""

    async def invoke(self, model_cfg: dict, prompt: str, params: dict,
                     system_prompt: str | None = None) -> JudgeResponse:
        adapter = OpenAIAdapter()
        return await adapter.invoke(model_cfg, prompt, params, system_prompt)


# ── Shared HTTP Client ───────────────────────────────────────────────────
#
# A single AsyncClient is reused across all judge calls so that connections
# (and TLS sessions) are pooled instead of being re-negotiated per request.
# This matters a lot when a task runs thousands of cases concurrently.

_SHARED_CLIENT: httpx.AsyncClient | None = None


def _get_shared_client() -> httpx.AsyncClient:
    """Return the process-wide pooled HTTP client for judge calls."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None or _SHARED_CLIENT.is_closed:
        _SHARED_CLIENT = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            follow_redirects=True,
        )
    return _SHARED_CLIENT


async def close_shared_client() -> None:
    """Close the shared client (called on application shutdown)."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is not None and not _SHARED_CLIENT.is_closed:
        await _SHARED_CLIENT.aclose()
    _SHARED_CLIENT = None


# ── Response Parser ──────────────────────────────────────────────────────

def _parse_judge_response(raw: str | None, model_name: str = "", latency_ms: float = 0.0) -> JudgeResponse:
    """Four-layer fallback parser for AI judge responses."""

    if raw is None:
        raw = ""
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

    # Layer 4: default fallback — mark as a parse failure rather than a real 0 score
    result.score = 0.0
    result.reasoning = raw[:500] if raw else "No response from judge model"
    result.error_kind = ERROR_PARSE if raw else ERROR_EMPTY
    result.error = (
        f"Judge response could not be parsed as JSON ({result.error_kind})"
    )
    # Parsing failures are almost always caused by truncated output (max_tokens),
    # so retrying with identical parameters would reproduce the same failure.
    result.retryable = False
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

    async def invoke(self, model_cfg: dict, prompt: str, params: dict | None = None,
                     system_prompt: str | None = None) -> JudgeResponse:
        provider = model_cfg.get("provider", "openai")
        adapter_cls = self._adapters.get(provider, OpenAIAdapter)
        adapter = adapter_cls()
        return await adapter.invoke(model_cfg, prompt, params or {}, system_prompt)


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
