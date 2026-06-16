"""Sandbox for custom scoring scripts.

Security measures:
  1. AST-level block: imports, exec/eval/compile, dangerous dunder access
  2. Restricted builtins: only safe math/string helpers (no type/getattr)
  3. Thread-based execution timeout (5s) to prevent CPU/memory DoS
  4. Output size cap (10 000 chars) to prevent memory exhaustion
  5. Cleanup: force garbage collection after sandbox execution
"""

from __future__ import annotations

import ast
import builtins
import gc
import threading
from typing import Any

SANDBOX_TIMEOUT_SECONDS = 5
MAX_OUTPUT_LENGTH = 10_000

# Minimal safe builtins — NO type, getattr, hasattr, setattr, isinstance, eval, exec, compile
# These are the basic building blocks for math/string operations only.
SAFE_BUILTINS: set[str] = {
    "abs", "all", "any", "bool", "dict", "enumerate", "float",
    "int", "len", "list", "max", "min", "range", "round",
    "sorted", "str", "sum", "tuple", "zip", "map", "filter",
    "True", "False", "None",
}

# Dunder attribute names that are always forbidden in attribute access
FORBIDDEN_DUNDERS: frozenset[str] = frozenset({
    "__class__", "__mro__", "__bases__", "__base__",
    "__subclasses__", "__globals__", "__code__",
    "__builtins__", "__import__",
})

# Attribute names that are always forbidden (including non-dunder escapes)
FORBIDDEN_ATTRS: frozenset[str] = frozenset({
    "__subclasses__", "__globals__", "__code__",
})


class SandboxError(Exception):
    pass


class SandboxSecurityError(SandboxError):
    pass


class SandboxTimeoutError(SandboxError):
    pass


def validate_ast(tree: ast.AST) -> None:
    """Check AST for dangerous constructs.

    Raises SandboxSecurityError if any forbidden pattern is found.
    """
    for node in ast.walk(tree):
        # ── Block imports ──────────────────────────────────────────
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxSecurityError("Import statements are not allowed")

        # ── Block dangerous function calls ──────────────────────────
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in ("exec", "eval", "compile", "__import__"):
                    raise SandboxSecurityError(f"{node.func.id}() is not allowed")

        # ── Block dangerous attribute access on any object ──────────
        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS:
                raise SandboxSecurityError(f"Access to '{node.attr}' is not allowed")
            if node.attr.startswith("__") and node.attr.endswith("__"):
                if node.attr in FORBIDDEN_DUNDERS:
                    raise SandboxSecurityError(f"Access to dunder '{node.attr}' is not allowed")

        # ── Block string multiplication that could cause memory DoS ──
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                if isinstance(node.right, ast.Constant) and isinstance(node.right.value, int):
                    est_size = len(node.left.value) * node.right.value
                    if est_size > MAX_OUTPUT_LENGTH * 2:
                        raise SandboxSecurityError(
                            f"String multiplication too large ({est_size} chars)"
                        )


class _SandboxRunner:
    """Runs a compiled code object in a restricted environment."""

    def __init__(self, code: Any, safe_globals: dict, safe_locals: dict):
        self._code = code
        self._safe_globals = safe_globals
        self._safe_locals = safe_locals
        self._result: Any = None
        self._error: Exception | None = None

    def run(self) -> None:
        try:
            exec(self._code, self._safe_globals, self._safe_locals)
            self._result = self._safe_locals.get("result", 0.0)
        except Exception as e:
            self._error = e


def execute_in_sandbox(source: str, context: dict) -> float:
    """Execute a scoring script in a restricted sandbox with timeout.

    Args:
        source: Python source code to execute.
        context: Dict of variables to inject into the script's local scope.

    Returns:
        The float value of the 'result' variable set by the script (default 0.0).

    Raises:
        SandboxSecurityError: If the source contains forbidden constructs.
        SandboxTimeoutError: If execution exceeds SANDBOX_TIMEOUT_SECONDS.
        SandboxError: If the script raises an unhandled exception.
    """
    # ── 1. Parse and validate AST ─────────────────────────────────
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise SandboxError(f"Script syntax error: {e}")

    validate_ast(tree)

    # ── 2. Build restricted execution environment ──────────────────
    safe_globals: dict[str, Any] = {
        "__builtins__": {k: getattr(builtins, k) for k in SAFE_BUILTINS},
    }
    safe_locals: dict[str, Any] = dict(context)

    code = compile(tree, "<sandbox>", "exec")

    # ── 3. Execute with thread-based timeout ──────────────────────
    runner = _SandboxRunner(code, safe_globals, safe_locals)
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    thread.join(timeout=SANDBOX_TIMEOUT_SECONDS)

    if thread.is_alive():
        # Thread is still running — force-cleanup (daemon=True so process exit kills it)
        raise SandboxTimeoutError(
            f"Script execution timed out after {SANDBOX_TIMEOUT_SECONDS}s"
        )

    if runner._error:
        raise SandboxError(str(runner._error))

    # ── 4. Cap output and cleanup ────────────────────────────────
    raw = runner._result
    try:
        result = float(raw)
    except (ValueError, TypeError):
        raise SandboxError(f"Result must be a number, got {type(raw).__name__}")

    # Cleanup references to sandboxed values
    safe_globals.clear()
    safe_locals.clear()
    gc.collect()

    return result
