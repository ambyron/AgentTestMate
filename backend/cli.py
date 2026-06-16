"""AgentMate CLI — Typer-based command-line interface."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

cli = typer.Typer(name="agentmate", help="AgentMate — AI Agent Testing Framework")
console = Console()

API_BASE = "http://localhost:8080/api/v1"


# ── Helper ──────────────────────────────────────────────────

def _api_url(path: str) -> str:
    return f"{API_BASE}{path}"


async def _get(path: str):
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(_api_url(path))
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, data: dict = None):
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(_api_url(path), json=data or {})
        resp.raise_for_status()
        return resp.json()


# ── Serve ───────────────────────────────────────────────────

@cli.command()
def serve(
    port: int = typer.Option(8080, help="Port to listen on"),
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    db: str = typer.Option("./data/agenteval.db", help="Database path"),
):
    """Start the AgentMate API server."""
    import os
    os.environ["TESTHUB_PORT"] = str(port)
    os.environ["TESTHUB_HOST"] = host
    os.environ["TESTHUB_DATABASE_URL"] = f"sqlite+aiosqlite:///{db}"
    console.print(f"[green]Starting AgentMate on {host}:{port}...[/green]")
    from app.main import run
    run()


# ── Run ─────────────────────────────────────────────────────

@cli.command()
def run_test(
    agent: str = typer.Option(..., "--agent", help="Agent ID"),
    dataset: str = typer.Option(..., "--dataset", help="Dataset ID"),
    concurrency: int = typer.Option(10, "--concurrency", "-c"),
    timeout: int = typer.Option(30, "--timeout", "-t"),
    max_retries: int = typer.Option(3, "--max-retries", "-r"),
    format: str = typer.Option("text", "--format", "-f"),
):
    """Run a test task via CLI (non-interactive)."""
    async def _run():
        task = await _post("/tasks", {
            "name": f"CLI Run: agent={agent}, dataset={dataset}",
            "agent_ids": [agent],
            "dataset_ids": [dataset],
            "concurrency": concurrency,
            "timeout_ms": timeout * 1000,
            "max_retries": max_retries,
        })
        task_id = task["id"]

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
            progress.add_task(description="Running tests...", total=None)

            # Start
            await _post(f"/tasks/{task_id}/start")

            # Poll for completion
            while True:
                t = await _get(f"/tasks/{task_id}")
                if t["status"] in ("completed", "failed", "cancelled"):
                    break
                await asyncio.sleep(1)

        summary = await _get(f"/tasks/{task_id}/summary")
        if format == "json":
            console.print(json.dumps(summary, indent=2))
        else:
            console.print(f"\n[bold]Results:[/bold]")
            console.print(f"  Total:  {summary['total']}")
            console.print(f"  Passed: {summary['passed']}")
            console.print(f"  Failed: {summary['failed']}")
            console.print(f"  Pass Rate: {summary['pass_rate']*100:.1f}%")
            console.print(f"  Avg Score: {summary['avg_score']:.4f}")

        sys.exit(0 if summary["failed"] == 0 else 1)

    asyncio.run(_run())


# ── Import ──────────────────────────────────────────────────

@cli.command()
def import_dataset(
    file: Path = typer.Option(..., "--file", "-f", help="Dataset file path"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Dataset name"),
):
    """Import a dataset from file."""
    async def _import():
        import httpx
        async with httpx.AsyncClient() as client:
            files = {"file": (file.name, file.read_bytes())}
            resp = await client.post(_api_url("/datasets/import"), files=files)
            resp.raise_for_status()
            result = resp.json()
        console.print(f"[green]Imported dataset:[/green] {result['dataset']['name']} ({result['cases_imported']} cases)")
    asyncio.run(_import())


# ── Report ──────────────────────────────────────────────────

@cli.command()
def report(
    task: str = typer.Option(..., "--task", "-t", help="Task ID"),
    format: str = typer.Option("html", "--format", "-f", help="Report format"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export a task report."""
    async def _report():
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(_api_url(f"/tasks/{task}/report"), params={"format": format})
            resp.raise_for_status()
            content = resp.text

        out_path = output or Path(f"report_{task}.{format}")
        out_path.write_text(content, encoding="utf-8")
        console.print(f"[green]Report saved to:[/green] {out_path}")
    asyncio.run(_report())


# ── List ────────────────────────────────────────────────────

@cli.command()
def list(
    resource: str = typer.Argument(..., help="Resource type: agents, tasks, datasets, rules, ai-judges"),
    status: Optional[str] = typer.Option(None, "--status", "-s"),
):
    """List resources."""
    async def _list():
        if resource == "agents":
            items = await _get(f"/agents?status={status or ''}")
            table = Table(title="Agents")
            table.add_column("ID", style="dim")
            table.add_column("Name")
            table.add_column("URL")
            table.add_column("Status")
            for a in items:
                table.add_row(a["id"][:8], a["name"], a["api_base_url"][:40], a["status"])
            console.print(table)
        elif resource == "tasks":
            items = await _get(f"/tasks?status={status or ''}")
            table = Table(title="Tasks")
            table.add_column("ID")
            table.add_column("Name")
            table.add_column("Status")
            table.add_column("Progress")
            for t in items:
                prog = t.get("progress", {})
                prog_str = f"{prog.get('completed', 0)}/{prog.get('total', 0)}"
                table.add_row(t["id"][:8], t["name"], t["status"], prog_str)
            console.print(table)
        elif resource == "datasets":
            items = await _get("/datasets")
            table = Table(title="Datasets")
            table.add_column("ID")
            table.add_column("Name")
            table.add_column("Type")
            for d in items:
                table.add_row(d["id"][:8], d["name"], d.get("dataset_type", "") or "")
            console.print(table)
        elif resource == "rules":
            items = await _get(f"/rules?enabled={status or 'true'}")
            table = Table(title="Rules")
            table.add_column("ID")
            table.add_column("Name")
            table.add_column("Type")
            table.add_column("Enabled")
            for r in items:
                table.add_row(r["id"][:8], r["name"], r["type"], str(r["enabled"]))
            console.print(table)
        elif resource in ("ai-judges", "ai_judges"):
            items = await _get("/ai-judges")
            table = Table(title="AI Judges")
            table.add_column("ID")
            table.add_column("Name")
            table.add_column("Provider")
            table.add_column("Model")
            table.add_column("Status")
            for j in items:
                table.add_row(j["id"][:8], j["name"], j["provider"], j["model_name"], j["status"])
            console.print(table)
        else:
            console.print(f"[red]Unknown resource: {resource}[/red]")
            raise typer.Exit(1)

    asyncio.run(_list())


# ── AI Judge Check ─────────────────────────────────────────

@cli.command()
def ai_judge_check(
    id: str = typer.Option(..., "--id", help="AI Judge model ID"),
):
    """Check connectivity of an AI judge model."""
    async def _check():
        result = await _post(f"/ai-judges/{id}/check")
        if result.get("reachable"):
            console.print(f"[green]✓ AI Judge is reachable[/green]")
            console.print(f"  Response: {result.get('response', '')[:100]}")
        else:
            console.print(f"[red]✗ AI Judge unreachable: {result.get('error')}[/red]")
            sys.exit(1)
    asyncio.run(_check())


# ── Eval Prompt Test ───────────────────────────────────────

@cli.command(name="eval-prompt-test")
def eval_prompt_test(
    prompt_id: str = typer.Option(..., "--prompt-id", help="Prompt template ID"),
    input: str = typer.Option("", "--input", help="Test input"),
    output: str = typer.Option("", "--output", help="Test actual output"),
    expected: str = typer.Option("", "--expected", help="Test expected output"),
):
    """Test an eval prompt template with sample data."""
    async def _test():
        result = await _post(f"/eval-prompts/{prompt_id}/test", {
            "input": input, "actual_output": output, "expected_output": expected,
        })
        console.print("[bold]Rendered Prompt:[/bold]")
        console.print(result.get("rendered_prompt", ""))
    asyncio.run(_test())


# ── Init ────────────────────────────────────────────────────

@cli.command()
def init(
    db: str = typer.Option("./data/agentmate.db", "--db", help="Database path"),
):
    """Initialize the database."""
    import os
    os.environ["TESTHUB_DATABASE_URL"] = f"sqlite+aiosqlite:///{db}"

    async def _init():
        from app.models import Base
        from app.__init_db import engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        console.print(f"[green]Database initialized: {db}[/green]")
        await engine.dispose()

    asyncio.run(_init())


if __name__ == "__main__":
    cli()
