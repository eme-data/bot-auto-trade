import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12


def _get_secret() -> str:
    return os.environ["JWT_SECRET"]


def _get_credentials() -> tuple[str, str]:
    return os.environ["DASH_USER"], os.environ["DASH_PASS"]


def create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": username, "exp": expire}, _get_secret(), algorithm=ALGORITHM
    )


def verify_credentials(username: str, password: str) -> bool:
    expected_user, expected_pass = _get_credentials()
    user_ok = secrets.compare_digest(username, expected_user)
    pass_ok = secrets.compare_digest(password, expected_pass)
    return user_ok and pass_ok


def get_current_user(request: Request, access_token: str | None = Cookie(default=None)) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(access_token, _get_secret(), algorithms=[ALGORITHM])
        username: str = payload.get("sub", "")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user_or_redirect(
    request: Request, access_token: str | None = Cookie(default=None)
) -> str | None:
    if not access_token:
        return None
    try:
        payload = jwt.decode(access_token, _get_secret(), algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
