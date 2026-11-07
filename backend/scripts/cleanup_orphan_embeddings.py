"""Remove vector rows that belong to users that no longer exist.

Usage (from backend/):

    python scripts/cleanup_orphan_embeddings.py --dry-run
    python scripts/cleanup_orphan_embeddings.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from core.database.session import engine  # noqa: E402

COUNT_SQL = text(
    "SELECT count(*) FROM embeddings e "
    "WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = e.user_id)"
)
DELETE_SQL = text(
    "DELETE FROM embeddings e "
    "WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id = e.user_id)"
)


async def main(apply: bool) -> None:
    async with engine.begin() as conn:
        orphaned = int((await conn.execute(COUNT_SQL)).scalar() or 0)
        print(f"orphaned embeddings: {orphaned}")
        if not apply or orphaned == 0:
            return
        result = await conn.execute(DELETE_SQL)
        print(f"deleted embeddings: {int(result.rowcount or 0)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.apply and not args.dry_run:
        parser.error("choose --dry-run or --apply")
    asyncio.run(main(args.apply))
