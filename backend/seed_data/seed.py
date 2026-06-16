"""
Seed script — imports objectives, rules, and debug test dataset into the system.

Usage:
    cd backend
    python -m seed_data.seed

This will:
  1. Import 5 evaluation objectives and 7 scoring rules
  2. Import 10 test cases across all objective combinations
"""

import asyncio
import json
from pathlib import Path

import httpx

BASE = "http://localhost:8000/api/v1"

HERE = Path(__file__).parent


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        # Step 1: Import objectives & rules
        print("=== Importing objectives & rules ===")
        with open(HERE / "objectives_rules.json") as f:
            payload = json.load(f)
        r = await c.post("/rules/import", json=payload)
        print(f"  Status: {r.status_code}")
        print(f"  Result: {r.json()}")

        # Step 2: Import debug dataset
        print("\n=== Importing debug test dataset ===")
        with open(HERE / "debug_dataset.json", "rb") as f:
            files = {"file": ("debug_dataset.json", f, "application/json")}
            r = await c.post("/datasets/import", files=files)
        print(f"  Status: {r.status_code}")
        print(f"  Result: {r.json()}")

        # Step 3: Verify
        print("\n=== Verification ===")
        r = await c.get("/objectives")
        objs = r.json()
        print(f"  Objectives ({len(objs)}): {[o['name'] for o in objs]}")

        r = await c.get("/rules")
        rules = r.json()
        print(f"  Rules ({len(rules)}): {[o['name'] for o in rules]}")

        r = await c.get("/datasets")
        dss = r.json()
        for ds in dss:
            print(f"  Dataset: {ds['name']} (id={ds['id']})")


if __name__ == "__main__":
    asyncio.run(main())
