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
            "seq": 1, "id": "builtin_simple", "name": "通用评分 (默认)", "description": "通用 AI 评估评分模板",
            "strategy": "simple", "is_builtin": 1, "version": "1.0",
            "system_prompt": "You are an expert AI evaluation judge. Assess the quality of the AI's response based on accuracy, completeness, and clarity.",
            "user_prompt_template": (
                "## Input\n{{input}}\n\n"
                "## Actual Output\n{{actual_output}}\n\n"
                "{% if criteria %}\n## Criteria\n{{criteria}}\n{% endif %}\n\n"
                "Evaluate the response quality. Provide a score between 0.0 and 1.0.\n"
                "## Output Format\n"
                '```json\n{"reasoning": "Your analysis...", "score": 0.85}\n```'
            ),
            "output_schema": _json.dumps({"score": "number 0-1", "reasoning": "string"}),
            "output_format": "json", "template_content": "", "variables": _empty_json,
            "created_at": now, "updated_at": now,
        },
        {
            "seq": 2, "id": "builtin_reference", "name": "参照对比 (默认)", "description": "基于预期输出进行参照对比评分",
            "strategy": "reference", "is_builtin": 1, "version": "1.0",
            "system_prompt": "You are an expert AI evaluation judge. Compare the actual output with the expected output (reference).",
            "user_prompt_template": (
                "## Input\n{{input}}\n\n"
                "## Expected Output (Reference)\n{{expected_output}}\n\n"
                "## Actual Output\n{{actual_output}}\n\n"
                "Score how well the actual output matches the expected output in terms of:\n"
                "- Accuracy: Does it contain the correct information?\n"
                "- Completeness: Does it cover all aspects of the expected output?\n"
                "- Clarity: Is it well-structured and clear?\n"
                "Provide a score between 0.0 and 1.0.\n"
                "## Output Format\n"
                '```json\n{"reasoning": "Your comparative analysis...", '
                '"score": 0.85, '
                '"dimension_scores": {"accuracy": 0.9, "completeness": 0.8, "clarity": 0.85}}\n```'
            ),
            "output_schema": _json.dumps({"score": "number 0-1", "reasoning": "string", "dimensions": {"accuracy": "number", "completeness": "number", "clarity": "number"}}),
            "output_format": "json", "template_content": "", "variables": _empty_json,
            "created_at": now, "updated_at": now,
        },
        {
            "seq": 3, "id": "builtin_rubric", "name": "多维度评分 (默认)", "description": "按评分维度逐一打分",
            "strategy": "rubric", "is_builtin": 1, "version": "1.0",
            "system_prompt": "You are an expert AI evaluation judge. Score the response using the provided rubric dimensions.",
            "user_prompt_template": (
                "## Input\n{{input}}\n\n"
                "## Actual Output\n{{actual_output}}\n\n"
                "{% if expected_output %}"
                "## Expected Output (Reference)\n{{expected_output}}\n\n"
                "{% endif %}"
                "## Scoring Rubric\n{{rubric}}\n\n"
                "Score each dimension in the rubric independently, then provide a weighted overall score.\n"
                "## Output Format\n"
                '```json\n{"reasoning": "Your analysis for each dimension...", '
                '"score": 0.85, '
                '"dimension_scores": {"dimension_name": 0.9}}\n```'
            ),
            "output_schema": _json.dumps({"score": "number 0-1", "reasoning": "string", "dimensions": "object"}),
            "output_format": "json", "template_content": "", "variables": _empty_json,
            "created_at": now, "updated_at": now,
        },
        {
            "seq": 4, "id": "builtin_cot", "name": "思维链评分 (默认)", "description": "逐步推理后再给出评分",
            "strategy": "chain_of_thought", "is_builtin": 1, "version": "1.0",
            "system_prompt": "You are an expert AI evaluation judge. Before giving the final score, reason step-by-step.",
            "user_prompt_template": (
                "## Input\n{{input}}\n\n"
                "## Actual Output\n{{actual_output}}\n\n"
                "{% if criteria %}\n## Scoring Criteria\n{{criteria}}\n{% endif %}\n\n"
                "Please follow these steps:\n"
                "1. Understand the evaluation criteria\n"
                "2. Analyze the actual output's key elements\n"
                "3. Compare against expectations point by point\n"
                "4. Provide your reasoning and final score\n"
                "## Output Format\n"
                '```json\n{"reasoning": "Step-by-step analysis...", "score": 0.85}\n```'
            ),
            "output_schema": _json.dumps({"score": "number 0-1", "reasoning": "string"}),
            "output_format": "json", "template_content": "", "variables": _empty_json,
            "created_at": now, "updated_at": now,
        },
        {
            "seq": 5, "id": "builtin_fewshot", "name": "少样本评分 (默认)", "description": "参考示例进行评分",
            "strategy": "few_shot", "is_builtin": 1, "version": "1.0",
            "system_prompt": "You are an expert AI evaluation judge. Use the provided examples to guide your scoring.",
            "user_prompt_template": (
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
                "Follow the format from the examples above.\n"
                "## Output Format\n"
                '```json\n{"reasoning": "Your analysis...", "score": 0.85}\n```'
            ),
            "output_schema": _json.dumps({"score": "number 0-1", "reasoning": "string"}),
            "output_format": "json", "template_content": "", "variables": _empty_json,
            "few_shot_examples": _json.dumps([]),
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
