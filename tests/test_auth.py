from pathlib import Path

import httpx

from paper_agent.auth import (
    AuthenticationService,
    InMemorySessionStore,
    PasswordHasher,
    RedisSessionStore,
)
from paper_agent.storage import PaperLibrary
from paper_agent.web_app import ResearchTaskManager, SESSION_COOKIE, create_app


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.closed = False

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.expirations[key] = ex

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.expirations.pop(key, None)

    async def aclose(self) -> None:
        self.closed = True


def test_password_hash_is_salted_and_verifiable() -> None:
    hasher = PasswordHasher()
    first = hasher.hash("correct horse battery staple")
    second = hasher.hash("correct horse battery staple")

    assert first != second
    assert "correct horse" not in first
    assert hasher.verify("correct horse battery staple", first)
    assert not hasher.verify("wrong password", first)


async def test_redis_session_store_hashes_token_and_refreshes_ttl() -> None:
    client = FakeRedis()
    sessions = RedisSessionStore(client, ttl_seconds=3600)

    token = await sessions.create(42)

    assert token not in next(iter(client.values))
    assert await sessions.resolve(token) == 42
    assert next(iter(client.expirations.values())) == 3600
    await sessions.delete(token)
    assert await sessions.resolve(token) is None
    await sessions.close()
    assert client.closed is True


async def test_register_login_persists_across_app_instances(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    sessions = InMemorySessionStore(ttl_seconds=3600)
    auth = AuthenticationService(library, sessions)
    manager = ResearchTaskManager(tmp_path / "reports", library=library)
    app = create_app(manager=manager, auth_service=auth, require_auth=True)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        protected = await client.get("/api/library/papers")
        assert protected.status_code == 401

        registered = await client.post(
            "/api/auth/register",
            json={
                "username": "researcher",
                "email": "researcher@example.com",
                "password": "a-secure-password",
            },
        )
        assert registered.status_code == 201
        assert registered.json()["username"] == "researcher"
        assert "HttpOnly" in registered.headers["set-cookie"]
        assert "SameSite=lax" in registered.headers["set-cookie"]
        token = client.cookies.get(SESSION_COOKIE)

        assert (await client.get("/api/auth/me")).status_code == 200
        assert (await client.get("/api/library/papers")).status_code == 200

    restarted_auth = AuthenticationService(library, sessions)
    restarted_app = create_app(
        manager=manager,
        auth_service=restarted_auth,
        require_auth=True,
    )
    restarted_transport = httpx.ASGITransport(app=restarted_app)
    async with httpx.AsyncClient(
        transport=restarted_transport,
        base_url="http://test",
        cookies={SESSION_COOKIE: token},
    ) as client:
        restored = await client.get("/api/auth/me")
        assert restored.status_code == 200
        assert restored.json()["email"] == "researcher@example.com"

        logged_out = await client.post("/api/auth/logout")
        assert logged_out.status_code == 204
        assert (await client.get("/api/auth/me")).status_code == 401

    library.close()


async def test_login_rejects_wrong_password_and_duplicate_user(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    auth = AuthenticationService(library, InMemorySessionStore())
    manager = ResearchTaskManager(tmp_path / "reports", library=library)
    app = create_app(manager=manager, auth_service=auth, require_auth=True)
    transport = httpx.ASGITransport(app=app)

    payload = {
        "username": "reader",
        "email": "reader@example.com",
        "password": "long-enough-password",
    }
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        assert (await client.post("/api/auth/register", json=payload)).status_code == 201
        assert (await client.post("/api/auth/register", json=payload)).status_code == 409

        client.cookies.clear()
        rejected = await client.post(
            "/api/auth/login",
            json={"identifier": "reader", "password": "wrong-password"},
        )
        assert rejected.status_code == 401

        accepted = await client.post(
            "/api/auth/login",
            json={"identifier": "reader@example.com", "password": payload["password"]},
        )
        assert accepted.status_code == 200

    library.close()
