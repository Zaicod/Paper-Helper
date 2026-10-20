"""services auth implementation."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from typing import Protocol

try:
    import redis.asyncio as redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - dependency is part of the web extra
    redis = None  # type: ignore[assignment]
    RedisError = Exception  # type: ignore[assignment,misc]

from paper_agent.storage.library import PaperLibrary, UserView


class AuthenticationError(RuntimeError):
    pass


class SessionStoreError(RuntimeError):
    pass


class SessionStore(Protocol):
    ttl_seconds: int

    async def create(self, user_id: int) -> str: ...

    async def resolve(self, token: str) -> int | None: ...

    async def delete(self, token: str) -> None: ...

    async def close(self) -> None: ...


class PasswordHasher:
    """Versioned scrypt password hashes using only Python's standard library."""

    n = 2**14
    r = 8
    p = 1
    dklen = 32

    def hash(self, password: str) -> str:
        _validate_password(password)
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=self.n,
            r=self.r,
            p=self.p,
            dklen=self.dklen,
        )
        return "$".join(
            [
                "scrypt",
                str(self.n),
                str(self.r),
                str(self.p),
                _b64(salt),
                _b64(derived),
            ]
        )

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt, expected = encoded.split("$")
            if algorithm != "scrypt":
                return False
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=_unb64(salt),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(_unb64(expected)),
            )
            return hmac.compare_digest(derived, _unb64(expected))
        except (ValueError, TypeError):
            return False


class RedisSessionStore:
    key_prefix = "paperflow:session:"

    def __init__(self, client: object, ttl_seconds: int = 7 * 24 * 3600) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds

    @classmethod
    def from_url(
        cls, url: str, ttl_seconds: int = 7 * 24 * 3600
    ) -> RedisSessionStore:
        if redis is None:
            raise RuntimeError('Redis support is missing; install with ".[web]"')
        client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        return cls(client, ttl_seconds)

    async def create(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        value = json.dumps({"user_id": user_id}, separators=(",", ":"))
        try:
            await self.client.set(self._key(token), value, ex=self.ttl_seconds)
        except RedisError as exc:
            raise SessionStoreError("Redis 会话服务不可用") from exc
        return token

    async def resolve(self, token: str) -> int | None:
        if not token:
            return None
        key = self._key(token)
        try:
            value = await self.client.get(key)
            if value is None:
                return None
            await self.client.expire(key, self.ttl_seconds)
        except RedisError as exc:
            raise SessionStoreError("Redis 会话服务不可用") from exc
        try:
            user_id = int(json.loads(value)["user_id"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            await self.client.delete(key)
            return None
        return user_id

    async def delete(self, token: str) -> None:
        if not token:
            return
        try:
            await self.client.delete(self._key(token))
        except RedisError as exc:
            raise SessionStoreError("Redis 会话服务不可用") from exc

    async def close(self) -> None:
        await self.client.aclose()

    def _key(self, token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"{self.key_prefix}{digest}"


class InMemorySessionStore:
    """Test-only session store; production uses RedisSessionStore."""

    def __init__(self, ttl_seconds: int = 7 * 24 * 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self.sessions: dict[str, int] = {}

    async def create(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        self.sessions[token] = user_id
        return token

    async def resolve(self, token: str) -> int | None:
        return self.sessions.get(token)

    async def delete(self, token: str) -> None:
        self.sessions.pop(token, None)

    async def close(self) -> None:
        return None


@dataclass(frozen=True)
class AuthenticatedSession:
    user: UserView
    token: str


class AuthenticationService:
    def __init__(
        self,
        library: PaperLibrary,
        sessions: SessionStore,
        hasher: PasswordHasher | None = None,
    ) -> None:
        self.library = library
        self.sessions = sessions
        self.hasher = hasher or PasswordHasher()

    async def register(
        self, username: str, email: str, password: str
    ) -> AuthenticatedSession:
        _validate_password(password)
        password_hash = await asyncio.to_thread(self.hasher.hash, password)
        user = await asyncio.to_thread(
            self.library.create_user, username, email, password_hash
        )
        token = await self.sessions.create(user.id)
        return AuthenticatedSession(user=user, token=token)

    async def login(self, identifier: str, password: str) -> AuthenticatedSession:
        record = await asyncio.to_thread(
            self.library.get_user_credentials, identifier
        )
        if record is None or not await asyncio.to_thread(
            self.hasher.verify, password, record.password_hash
        ):
            raise AuthenticationError("用户名、邮箱或密码不正确")
        token = await self.sessions.create(record.user.id)
        return AuthenticatedSession(user=record.user, token=token)

    async def current_user(self, token: str) -> UserView | None:
        user_id = await self.sessions.resolve(token)
        if user_id is None:
            return None
        return self.library.get_user(user_id)

    async def logout(self, token: str) -> None:
        await self.sessions.delete(token)

    async def close(self) -> None:
        await self.sessions.close()


def _validate_password(password: str) -> None:
    if not 8 <= len(password) <= 128:
        raise ValueError("密码长度必须为 8 到 128 个字符")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
