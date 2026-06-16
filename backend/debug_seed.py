"""Debug - try regular INSERT to see error."""
import asyncio
from app.__init_db import engine
from sqlalchemy import text


async def test():
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "INSERT INTO eval_prompt_templates "
                "(id, name, strategy, is_builtin, version, user_prompt_template, output_format) "
                "VALUES ('test_err', 'Test', 'simple', 1, '1.0', 'hello', 'json')"
            ))
            print("Regular insert OK")
        except Exception as e:
            print(f"Regular insert ERROR: {e}")

        await conn.execute(text("DELETE FROM eval_prompt_templates WHERE id = 'test_err'"))

    await engine.dispose()


asyncio.run(test())
