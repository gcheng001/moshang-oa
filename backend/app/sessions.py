"""In-memory sessions backed by an optional operating-system credential vault."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from . import credentials, oa

TOKEN_TTL_SECONDS = 20 * 60  # refresh proactively well before OA expiry


@dataclass
class Session:
    username: str
    password: str
    base_url: str
    token: str
    profile: dict[str, Any]
    can_approve: bool
    token_at: float = field(default_factory=time.time)


_lock = threading.Lock()
_sessions: dict[str, Session] = {}


def _profile(base_url: str, token: str, login_info: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = oa.get_profile(base_url, token)
    except Exception:
        profile = {}
    organizations = login_info.get("Orgnizations") or []
    first_org = organizations[0] if organizations and isinstance(organizations[0], dict) else {}
    return {
        "userId": profile.get("userId") or login_info.get("UserId"),
        "userName": profile.get("userName") or login_info.get("UserName"),
        "employeeId": profile.get("employeeId"),
        "employeeName": profile.get("employeeName") or login_info.get("DisplayName"),
        "lawfirmName": profile.get("lawfirmName") or first_org.get("Name"),
    }


def _create(base_url: str, username: str, password: str) -> tuple[str, Session]:
    token, _ = oa.login_with_password(base_url, username, password)
    # Account/Login only promises an access token.  MenuPermissions must come
    # from the authenticated account snapshot, otherwise a UI-only role check
    # could accidentally expose approval to a non-approver.
    login_info = oa.get_login_info(base_url, token)
    profile = _profile(base_url, token, login_info)
    session = Session(
        username=username,
        password=password,
        base_url=base_url,
        token=token,
        profile=profile,
        can_approve=oa.has_filing_approval_permission(login_info),
    )
    session_id = secrets.token_hex(16)
    with _lock:
        _sessions[session_id] = session
    return session_id, session


def create(base_url: str, username: str, password: str, *, remember: bool) -> tuple[str, Session]:
    session_id, session = _create(base_url, username, password)
    if remember:
        try:
            credentials.save_password(username, password)
        except Exception:
            drop(session_id)
            raise
    else:
        # If this account was remembered previously, an unchecked box means
        # the user has explicitly opted it out of future automatic restore.
        try:
            if credentials.has_password(username):
                credentials.forget_password(username)
        except credentials.CredentialStoreUnavailable:
            # One-session login must remain available when no OS vault exists.
            pass
    return session_id, session


def restore(base_url: str) -> tuple[str, Session] | None:
    saved = credentials.load_last_login()
    if saved is None:
        return None
    return _create(base_url, saved.username, saved.password)


def get(session_id: str | None) -> Session | None:
    if not session_id:
        return None
    with _lock:
        session = _sessions.get(session_id)
    if session is None:
        return None
    if time.time() - session.token_at > TOKEN_TTL_SECONDS:
        session.token, _ = oa.login_with_password(session.base_url, session.username, session.password)
        login_info = oa.get_login_info(session.base_url, session.token)
        session.profile = _profile(session.base_url, session.token, login_info)
        session.can_approve = oa.has_filing_approval_permission(login_info)
        session.token_at = time.time()
    return session


def peek(session_id: str | None) -> Session | None:
    """Read a session without network refresh, for local cleanup paths."""
    if not session_id:
        return None
    with _lock:
        return _sessions.get(session_id)


def drop(session_id: str | None, *, forget_login: bool = False) -> None:
    session = None
    if session_id:
        with _lock:
            session = _sessions.pop(session_id, None)
    if not forget_login:
        return
    if session is not None:
        credentials.forget_password(session.username)
    else:
        # The backend may have restarted while the browser still holds an old
        # session id. Logout must still remove the remembered OS-vault login.
        credentials.forget_last_login()
