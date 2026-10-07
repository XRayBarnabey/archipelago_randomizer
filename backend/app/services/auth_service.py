import base64
import hashlib
import hmac
import json
import secrets
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import utcnow
from app.errors import TooManyAttempts, UnauthorizedError, ValidationFailed
from app.models import AdminCredential

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
MIN_PASSWORD_LENGTH = 4

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class LoginThrottle:
    """In-memory brute-force mitigation: lock a client out after too many consecutive failures."""

    def __init__(self):
        self._failures: dict[str, tuple[int, float]] = {}

    def check(self, key: str, settings: Settings) -> None:
        count, since = self._failures.get(key, (0, 0.0))
        if count >= settings.admin_max_failed_logins:
            if time.monotonic() - since < settings.admin_lockout_seconds:
                raise TooManyAttempts("Trop de tentatives échouées. Réessayez dans quelques minutes.")
            self._failures.pop(key, None)

    def failure(self, key: str) -> None:
        count, _ = self._failures.get(key, (0, 0.0))
        self._failures[key] = (count + 1, time.monotonic())

    def success(self, key: str) -> None:
        self._failures.pop(key, None)


throttle = LoginThrottle()


class AuthService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def credential(self) -> AdminCredential:
        """Return the credential row, seeding admin/admin on first use (idempotent)."""
        cred = self.db.scalar(select(AdminCredential).order_by(AdminCredential.id))
        if cred is None:
            cred = AdminCredential(
                username=DEFAULT_USERNAME,
                password_hash=hash_password(DEFAULT_PASSWORD),
                secret_key=secrets.token_hex(32),
                updated_at=utcnow(),
            )
            self.db.add(cred)
            self.db.commit()
        return cred

    def _secret(self, cred: AdminCredential) -> bytes:
        return (self.settings.admin_secret_key or cred.secret_key).encode()

    def _sign(self, cred: AdminCredential, payload: bytes) -> str:
        return _b64(hmac.new(self._secret(cred), payload, hashlib.sha256).digest())

    def is_default(self, cred: AdminCredential | None = None) -> bool:
        cred = cred or self.credential()
        return cred.username == DEFAULT_USERNAME and verify_password(DEFAULT_PASSWORD, cred.password_hash)

    def issue_token(self, cred: AdminCredential) -> tuple[str, int]:
        expires = int(time.time()) + self.settings.admin_token_ttl
        # the password hash fingerprint invalidates existing tokens when the credentials change
        fingerprint = hashlib.sha256(cred.password_hash.encode()).hexdigest()[:16]
        payload = json.dumps({"u": cred.username, "exp": expires, "f": fingerprint}).encode()
        return f"{_b64(payload)}.{self._sign(cred, payload)}", expires

    def verify_token(self, token: str | None) -> AdminCredential:
        error = UnauthorizedError("Authentification requise.")
        if not token:
            raise error
        cred = self.credential()
        try:
            body, signature = token.split(".")
            payload = _unb64(body)
            data = json.loads(payload)
        except (ValueError, TypeError):
            raise error from None
        if not hmac.compare_digest(signature, self._sign(cred, payload)):
            raise error
        fingerprint = hashlib.sha256(cred.password_hash.encode()).hexdigest()[:16]
        if data.get("exp", 0) < time.time() or data.get("f") != fingerprint or data.get("u") != cred.username:
            raise error
        return cred

    def login(self, username: str, password: str, client_key: str) -> tuple[str, int, AdminCredential]:
        throttle.check(client_key, self.settings)
        cred = self.credential()
        ok_user = hmac.compare_digest(username.encode(), cred.username.encode())
        ok_pass = verify_password(password, cred.password_hash)
        if not (ok_user and ok_pass):
            throttle.failure(client_key)
            if self.settings.admin_login_delay > 0:
                time.sleep(self.settings.admin_login_delay)
            raise UnauthorizedError("Identifiant ou mot de passe incorrect.")
        throttle.success(client_key)
        token, expires = self.issue_token(cred)
        return token, expires, cred

    def change_credentials(
        self, cred: AdminCredential, current: str, new_password: str, new_username: str | None
    ) -> tuple[str, int]:
        if not verify_password(current, cred.password_hash):
            raise UnauthorizedError("Mot de passe actuel incorrect.", code="INVALID_CURRENT_PASSWORD")
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValidationFailed(f"Le nouveau mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères.")
        if new_username:
            cred.username = new_username.strip() or cred.username
        cred.password_hash = hash_password(new_password)
        cred.updated_at = utcnow()
        self.db.commit()
        return self.issue_token(cred)
