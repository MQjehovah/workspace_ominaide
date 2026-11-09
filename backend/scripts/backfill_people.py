"""Build the people index from existing mail, calendar, notes and captures."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from core.auth.domain.models import User  # noqa: E402
from core.database.session import async_session  # noqa: E402
from ai.people.service import backfill_user  # noqa: E402


async def main(user_id: int | None) -> None:
    async with async_session() as db:
        if user_id is None:
            users = list((await db.execute(select(User.id).order_by(User.id))).scalars().all())
        else:
            users = [user_id]
    for uid in users:
        counts = await backfill_user(uid)
        print(f"user {uid}: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int)
    args = parser.parse_args()
    asyncio.run(main(args.user_id))
