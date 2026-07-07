"""In-memory session store for the local backend.

The app runs on localhost for a single user at a time; sessions map a random
session id to the user's OA apikey + token so the token can be refreshed
transparently when it expires.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from . import oa

TOKEN_TTL_SECONDS = 20 * 60  # refresh proactively well before OA expiry


@dataclass
class Session:
    api_key: str
    base_url: str
    token: str
    profile: dict[str, Any]
    token_at: float = field(default_factory=time.time)


_lock = threading.Lock()
_sessions: dict[str, Session] = {}


def create(base_url: str, api_key: str) -> tuple[str, Session]:
    token = oa.login(base_url, api_key)
    profile = oa.get_profile(base_url, token)
    session = Session(api_key=api_key, base_url=base_url, token=token, profile=profile)
    session_id = secrets.token_hex(16)
    with _lock:
        _sessions[session_id] = session
    return session_id, session


def get(session_id: str | None) -> Session | None:
    if not session_id:
        return None
    with _lock:
        session = _sessions.get(session_id)
    if session is None:
        return None
    if time.time() - session.token_at > TOKEN_TTL_SECONDS:
        session.token = oa.login(session.base_url, session.api_key)
        session.token_at = time.time()
    return session


def drop(session_id: str | None) -> None:
    if not session_id:
        return
    with _lock:
        _sessions.pop(session_id, None)
