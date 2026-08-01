import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_app.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["LLM_API_KEY"] = ""
os.environ["MINIO_ENDPOINT"] = "localhost:9000"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager


@pytest_asyncio.fixture(scope="session")
async def client():
    import main
    async with LifespanManager(main.app):
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
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}
