"""Task Execution Engine — concurrency-controlled agent testing."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

import httpx

from app.config import settings

logger = logging.getLogger("agentmate.engine")

# Ensure log file handler is set up once
if not logger.handlers:
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    # File handler
    log_path = settings.data_path / "logs" / "engine.log"
    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)


# ── Data Structures ────────────────────────────────────────

@dataclass
class AgentResponse:
    raw_output: str = ""
    status_code: int = 0
    response_time_ms: float = 0.0
    error: str | None = None


@dataclass
class ExecResult:
    """Result of executing a single test case against an agent."""
    case_id: str
    agent_id: str
    raw_input: str = ""
    raw_output: str = ""
    response_time_ms: float = 0.0
    status_code: int = 0
    error: str | None = None
    skipped: bool = False


# ── AgentInvoker ───────────────────────────────────────────

class AgentInvoker:
    """Invokes agent APIs with auth injection and timeout."""

    async def invoke(self, agent_cfg: dict, input_text: str, timeout_ms: int = 30_000,
                     case_id: str = "") -> AgentResponse:
        url = agent_cfg.get("api_base_url", "")
        method = agent_cfg.get("method", "POST").upper()
        headers = dict(agent_cfg.get("headers_template", {}))

        # Inject auth
        auth_type = agent_cfg.get("auth_type", "none")
        auth_creds = agent_cfg.get("auth_credentials", "")
        if auth_type == "bearer" and auth_creds:
            headers["Authorization"] = f"Bearer {auth_creds}"
        elif auth_type == "api_key" and auth_creds:
            headers["Authorization"] = f"Bearer {auth_creds}"
        elif auth_type == "basic" and auth_creds:
            headers["Authorization"] = f"Basic {auth_creds}"

        # Render template variables in headers (e.g. {{$timestamp}}, {{input}})
        rendered_headers = {}
        for k, v in headers.items():
            if isinstance(v, str):
                v = v.replace("{{$timestamp}}", str(int(time.time() * 1000)))
                v = v.replace("{{$TIMESTAMP}}", str(int(time.time() * 1000)))
                v = v.replace("{{input}}", input_text).replace("{{INPUT}}", input_text)
            rendered_headers[k] = v
        headers = rendered_headers

        body_template = agent_cfg.get("body_template", {})
        body = self._render_body(body_template, input_text)

        tag = f"[{case_id}] " if case_id else ""
        safe_headers = {k: (v[:20] + "…" if k.lower() in ("authorization", "x-api-key") and len(v) > 20 else v)
                        for k, v in headers.items()}
        logger.info("─" * 60)
        logger.info("%s>>> REQUEST  %s  %s", tag, method, url)
        logger.info("%s>>> Headers: %s", tag, json.dumps(safe_headers, ensure_ascii=False))
        logger.info("%s>>> Body:    %s", tag, json.dumps(body, ensure_ascii=False, indent=2))

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers, params=body)
                else:
                    resp = await client.request(method, url, headers=headers, json=body)
                elapsed = (time.monotonic() - start) * 1000
                resp_body = resp.text[:2000] + ("…" if len(resp.text) > 2000 else "")
                logger.info("%s<<< RESPONSE %s  [%s]  (%dms)", tag, url, resp.status_code, elapsed)
                logger.info("%s<<< Body:    %s", tag, resp_body[:500])
                # Treat non-2xx as errors so they are correctly counted as failed
                err = None
                if resp.status_code >= 400:
                    try:
                        detail = resp.json().get("error", {}).get("message", resp.text[:200])
                    except Exception:
                        detail = resp.text[:200]
                    err = f"HTTP {resp.status_code}: {detail}"
                    logger.warning("%s<<< API ERROR %s", tag, err)
                return AgentResponse(
                    raw_output=resp.text,
                    status_code=resp.status_code,
                    response_time_ms=elapsed,
                    error=err,
                )
        except httpx.TimeoutException:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning("%s<<< TIMEOUT  %s  (%dms)", tag, url, elapsed)
            return AgentResponse(error=f"Timeout after {timeout_ms}ms", response_time_ms=elapsed)
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.error("%s<<< ERROR    %s  %s", tag, url, e)
            return AgentResponse(error=str(e), response_time_ms=elapsed)

    def _render_body(self, template: dict, input_text: str) -> dict:
        """Render body template by replacing placeholders with input (recursive)."""
        def _replace(obj):
            if isinstance(obj, str):
                return obj.replace("{{input}}", input_text).replace("{{INPUT}}", input_text)
            if isinstance(obj, dict):
                return {k: _replace(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_replace(item) for item in obj]
            return obj
        rendered = _replace(template)
        if not rendered:
            return {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": input_text}],
            }
        return rendered


# ── RetryHandler ──────────────────────────────────────────

class RetryHandler:
    """Exponential backoff retry with jitter."""

    def __init__(self, max_retries: int = 3, base_delay_ms: float = 1000,
                 max_delay_ms: float = 60_000, jitter: float = 0.5):
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.jitter = jitter

    RETRYABLE_ERRORS = ("timeout", "connection", "500", "502", "503", "504", "429")

    async def execute(self, fn, *args, **kwargs) -> AgentResponse:
        last_error = None
        for attempt in range(self.max_retries + 1):
            result = await fn(*args, **kwargs)
            if result.error is None and result.status_code < 500:
                return result
            if result.status_code in (429, 500, 502, 503, 504) or (
                result.error and any(e in result.error.lower() for e in ("timeout", "connection"))
            ):
                last_error = result
                if attempt < self.max_retries:
                    delay = min(self.base_delay_ms * (2 ** attempt) + random.uniform(0, self.jitter * 1000),
                                self.max_delay_ms) / 1000
                    await asyncio.sleep(delay)
            else:
                return result
        last_error.error = (last_error.error or "") + f" (after {self.max_retries} retries)"
        return last_error


# ── TaskExecutionEngine ──────────────────────────────────

class TaskExecutionEngine:
    """Core concurrent test executor with pause/resume/cancel support."""

    def __init__(self, max_concurrency: int = 10, default_timeout_ms: int = 30_000,
                 max_retries: int = 3):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._cancel_flag = False
        self._timeout_ms = default_timeout_ms
        self._max_retries = max_retries
        self._invoker = AgentInvoker()
        self._retry = RetryHandler(max_retries=max_retries)
        self._results: list[ExecResult] = []

    async def execute(self, agent_cfg: dict, cases: list[dict]) -> AsyncIterator[ExecResult]:
        """Execute test cases concurrently and yield results as they complete."""
        self._cancel_flag = False
        self._results = []

        agent_label = agent_cfg.get("id", "?")[:12]
        total = len(cases)
        logger.info("=" * 60)
        logger.info("START  agent=%s  cases=%d", agent_label, total)

        async def _run_one(case: dict) -> ExecResult:
            async with self.semaphore:
                await self._pause_event.wait()
                if self._cancel_flag:
                    logger.info("SKIP   agent=%s  case=%s  (cancelled)", agent_label, case.get("case_id", "?"))
                    return ExecResult(case_id=case.get("case_id", ""), agent_id=agent_cfg.get("id", ""), skipped=True)
                case_id = case.get("case_id", "?")
                logger.info("RUN    agent=%s  case=%s", agent_label, case_id)
                resp = await self._retry.execute(
                    self._invoker.invoke, agent_cfg, case.get("input", ""), self._timeout_ms,
                    case_id=case_id,
                )
                if resp.error:
                    logger.warning("DONE   agent=%s  case=%s  ERROR: %s", agent_label, case_id, resp.error)
                else:
                    logger.info("DONE   agent=%s  case=%s  status=%s  time=%dms",
                                agent_label, case_id, resp.status_code, resp.response_time_ms)
                return ExecResult(
                    case_id=case.get("case_id", ""),
                    agent_id=agent_cfg.get("id", ""),
                    raw_input=case.get("input", ""),
                    raw_output=resp.raw_output,
                    response_time_ms=resp.response_time_ms,
                    status_code=resp.status_code,
                    error=resp.error,
                )

        tasks = [asyncio.create_task(_run_one(c)) for c in cases]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            self._results.append(result)
            yield result

        logger.info("END    agent=%s  completed=%d  failed=%d",
                    agent_label,
                    sum(1 for r in self._results if not r.error),
                    sum(1 for r in self._results if r.error))

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def cancel(self):
        self._cancel_flag = True
        self._pause_event.set()

    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_flag
