import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_app.db"
# 残留的旧测试库会让"首个注册用户=管理员"失效（admin 用例 403），每次会话先清掉
try:
    os.remove("./test_app.db")
except OSError:
    pass
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["LLM_API_KEY"] = ""
os.environ["JOBS_WORKERS"] = "0"
os.environ["ALLOW_REGISTRATION"] = "true"
# Use a closed port so MinIO startup probes fail fast in tests (no 15s DNS/connect wait).
os.environ["MINIO_ENDPOINT"] = "127.0.0.1:1"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager


@pytest_asyncio.fixture(scope="session")
async def client():
    import main
    # Local MinIO probes can take a couple of seconds; don't race the 5s default.
    async with LifespanManager(main.app, startup_timeout=30, shutdown_timeout=30):
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest_asyncio.fixture(scope="session")
async def admin_token(client):
    """First registered user becomes admin."""
    import random
    import string
    suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    username = f"admin_{suffix}"
    email = f"{username}@example.com"
    r = await client.post("/api/auth/register", json={"username": username, "email": email, "password": "testpass123"})
    assert r.status_code in (200, 201), r.text
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    await _set_admin(username, True)
    return r.json()["access_token"]


@pytest_asyncio.fixture(scope="session")
async def user_token(client):
    """A non-admin registered user."""
    import random
    import string
    suffix = "".join(random.choices(string.ascii_lowercase, k=6))
    username = f"user_{suffix}"
    email = f"{username}@example.com"
    r = await client.post("/api/auth/register", json={"username": username, "email": email, "password": "testpass123"})
    assert r.status_code in (200, 201), r.text
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    await _set_admin(username, False)
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _set_admin(username: str, value: bool) -> None:
    """Make fixture roles deterministic regardless of test registration order."""
    from sqlalchemy import select

    from core.auth.domain.models import User
    from core.database.session import async_session

    async with async_session() as db:
        row = (await db.execute(
            select(User).where(User.username == username)
        )).scalar_one()
        row.is_admin = value
        await db.commit()
