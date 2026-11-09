"""Tiny evaluation runner for retrieval/context quality.

Usage:
    python -m evals.run --user-id 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from ai.memory.graph.service import build_context

CASES = Path(__file__).parent / "cases"


async def run(user_id: int) -> int:
    passed = 0
    total = 0
    for path in sorted(CASES.glob("*.json")):
        cases = json.loads(path.read_text())
        for case in cases:
            total += 1
            result = await build_context(user_id, case.get("query", ""))
            types = {item.get("type") for item in result.get("items", [])}
            expected = set(case.get("expect_types", []))
            ok = (not expected) or bool(types & expected)
            print(
                f"[{'PASS' if ok else 'FAIL'}] {case.get('id')} "
                f"types={sorted(types)}"
            )
            if ok:
                passed += 1
    print(f"\n{passed}/{total} cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.user_id)))
