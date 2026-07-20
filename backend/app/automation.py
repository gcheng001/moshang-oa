"""Account-bound automatic filing approval with a deliberately safe shadow mode.

The scheduler runs only for a remembered, approval-capable account.  It never
uses browser storage and records every candidate/action locally.  The first
three days are shadow-only: the exact same rules run, but OA is not written.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import credentials, oa, sessions

POLL_SECONDS = 10 * 60
SHADOW_SECONDS = 3 * 24 * 60 * 60
STATE_DIR = Path.home() / ".office-assistant"
STATE_FILE = STATE_DIR / "approval-automation.json"
MAX_AUTO_REJECTIONS_PER_FINGERPRINT = 2

_lock = threading.RLock()
_run_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict[str, Any]:
    return {"version": 1, "accounts": {}}


def _read() -> dict[str, Any]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("accounts"), dict) else _default_state()
    except FileNotFoundError:
        return _default_state()
    except (OSError, json.JSONDecodeError):
        return _default_state()


def _write(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        STATE_DIR.chmod(0o700)
    except OSError:
        pass
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    temp.replace(STATE_FILE)


def _account(state: dict[str, Any], username: str) -> dict[str, Any]:
    accounts = state.setdefault("accounts", {})
    value = accounts.setdefault(username, {})
    value.setdefault("enabled", False)
    value.setdefault("shadow_started_at", None)
    value.setdefault("last_checked_at", None)
    value.setdefault("last_error", None)
    value.setdefault("events", [])
    value.setdefault("reject_counts", {})
    return value


def _events(account: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    events = account.get("events") or []
    return events[-limit:] if isinstance(events, list) else []


def _record(account: dict[str, Any], event: dict[str, Any]) -> None:
    events = account.setdefault("events", [])
    events.append({"at": _now(), **event})
    del events[:-100]


def _shadow_remaining(started_at: str | None) -> int:
    if not started_at:
        return SHADOW_SECONDS
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return SHADOW_SECONDS
    return max(0, int(SHADOW_SECONDS - (time.time() - started)))


def status(username: str) -> dict[str, Any]:
    with _lock:
        account = _account(_read(), username)
        remaining = _shadow_remaining(account.get("shadow_started_at")) if account.get("enabled") else 0
        return {
            "enabled": bool(account.get("enabled")),
            "mode": "shadow" if account.get("enabled") and remaining else "active",
            "shadow_remaining_seconds": remaining,
            "poll_minutes": POLL_SECONDS // 60,
            "last_checked_at": account.get("last_checked_at"),
            "last_error": account.get("last_error"),
            "events": list(reversed(_events(account, limit=20))),
        }


def record_event(username: str, event: dict[str, Any]) -> None:
    """记录一条事件（人工审批/驳回/反审等），供审批记录页查看。"""
    with _lock:
        state = _read()
        account = _account(state, username)
        _record(account, event)
        _write(state)


def history(username: str, limit: int = 100) -> list[dict[str, Any]]:
    """返回最新在前的事件列表（默认最多 100 条）。"""
    with _lock:
        account = _account(_read(), username)
        return list(reversed(_events(account, limit=limit)))


def set_enabled(session: sessions.Session, enabled: bool) -> dict[str, Any]:
    if enabled and not credentials.has_password(session.username):
        raise ValueError("请先勾选“保持登录”，自动审批才能在 Windows 常驻运行")
    if not enabled:
        disable(session.username)
        return status(session.username)
    with _lock:
        state = _read()
        account = _account(state, session.username)
        account["enabled"] = enabled
        account["last_error"] = None
        if enabled and not account.get("shadow_started_at"):
            account["shadow_started_at"] = _now()
            _record(account, {"kind": "automation_enabled", "message": "已开启：前三天仅模拟，不写入 OA"})
        _write(state)
    return status(session.username)


def disable(username: str) -> None:
    """Fail-closed switch used by logout and non-remembered login flows."""
    with _lock:
        state = _read()
        account = _account(state, username)
        was_enabled = bool(account.get("enabled"))
        account["enabled"] = False
        account["last_error"] = None
        if was_enabled:
            _record(account, {"kind": "automation_disabled", "message": "已关闭自动审批"})
        _write(state)


def _reject_fingerprint(review: dict[str, Any], lawcase_id: int) -> tuple[str, list[str]] | None:
    conflict = review.get("conflict") or {}
    duplicate = review.get("duplicate_filing") or {}
    reasons = list(conflict.get("blockers") or []) + list(duplicate.get("blockers") or [])
    if not reasons:
        return None
    # Counts belong to one materially identical submission, not merely to a
    # common Chinese reason string that may occur in unrelated cases.
    conflict_findings = [
        {
            key: finding.get(key)
            for key in ("case_id", "matched_name", "relation", "severity")
        }
        for finding in conflict.get("findings") or []
        if isinstance(finding, dict)
    ]
    duplicate_findings = [
        {
            key: finding.get(key)
            for key in (
                "case_id",
                "relation",
                "principal_overlap",
                "opponent_overlap",
                "cause_match",
                "cause",
            )
        }
        for finding in duplicate.get("findings") or []
        if isinstance(finding, dict)
    ]
    evidence = {
        "lawcase_id": lawcase_id,
        "reasons": sorted(str(reason).strip() for reason in reasons),
        "principals": sorted(str(name) for name in conflict.get("principals") or []),
        "opponents": sorted(str(name) for name in conflict.get("opponents") or []),
        "conflict_findings": conflict_findings,
        "duplicate_findings": duplicate_findings,
    }
    raw = json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16], reasons


def _decision(review: dict[str, Any], account: dict[str, Any], lawcase_id: int) -> tuple[str, str, list[str]]:
    """Return approve/reject/manual and an auditable reason.

    Only objectively confirmed active conflict/duplicate blockers can reject.
    Everything incomplete, ambiguous or requiring human judgement remains manual.
    """
    fingerprint = _reject_fingerprint(review, lawcase_id)
    if fingerprint:
        key, reasons = fingerprint
        count = int((account.get("reject_counts") or {}).get(key, 0))
        if count < MAX_AUTO_REJECTIONS_PER_FINGERPRINT:
            return "reject", key, reasons
        return "manual", key, ["同一冲突已自动驳回两次，第三次转人工"] + reasons
    errors = oa.approval_gate_errors(review)
    if errors:
        return "manual", "", errors
    return "approve", "", ["全部可机器核验的审批规则通过"]


def run_once(session: sessions.Session) -> dict[str, Any]:
    """Run one serialized check and reject duplicate UI/background invocations."""
    if not _run_lock.acquire(blocking=False):
        raise ValueError("自动审批检查正在进行，请稍后再试")
    try:
        return _run_once(session)
    finally:
        _run_lock.release()


def _run_once(session: sessions.Session) -> dict[str, Any]:
    """Run a single poll. This is callable from the UI's “立即检查” button."""
    with _lock:
        state = _read()
        account = _account(state, session.username)
        if not account.get("enabled"):
            raise ValueError("自动审批尚未开启")
        shadow = _shadow_remaining(account.get("shadow_started_at")) > 0

    rows: list[dict[str, Any]] = []
    page_index = 0
    while True:
        payload = oa.get_case_list(
            session.base_url,
            session.token,
            {"status": 1, "pageIndex": page_index, "pageSize": 100},
        )
        batch = [row for row in payload.get("data") or [] if isinstance(row, dict)]
        rows.extend(batch)
        try:
            total = int(payload.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        if len(batch) < 100 or (total and len(rows) >= total):
            break
        page_index += 1
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in rows:
        lawcase_id = oa.row_case_id(row)
        if not lawcase_id:
            continue
        detail = oa.get_case_detail(session.base_url, session.token, lawcase_id)
        if oa.row_status(detail) != 1:
            continue
        review = oa.build_approval_review(session.base_url, session.token, lawcase_id, detail)
        with _lock:
            state = _read()
            account = _account(state, session.username)
            action, fingerprint, reasons = _decision(review, account, lawcase_id)
            case_no = detail.get("no") or detail.get("preNo") or str(lawcase_id)
            event = {"kind": "candidate", "case_id": lawcase_id, "case_no": case_no, "action": action, "reasons": reasons}
            if shadow:
                event["kind"] = "shadow_candidate"
                event["message"] = "观察期：未写入 OA"
                _record(account, event)
                _write(state)
                results.append(event)
                continue
            if action == "manual":
                event["message"] = "需要人工处理"
                _record(account, event)
                _write(state)
                results.append(event)
                continue

        # The user may disable automation while a slow review is running.
        # Recheck immediately before every write so the switch is fail-closed.
        with _lock:
            state = _read()
            account = _account(state, session.username)
            if not account.get("enabled"):
                event["kind"] = "automation_stopped"
                event["message"] = "自动审批已关闭，本次检查停止且未写入 OA"
                _record(account, event)
                _write(state)
                results.append(event)
                break

        # Review can involve several OA reads. Confirm the status again at the
        # last safe moment to avoid racing a manual approver or another device.
        fresh_detail = oa.get_case_detail(session.base_url, session.token, lawcase_id)
        fresh_status = oa.row_status(fresh_detail)
        if fresh_status != 1:
            event["kind"] = "status_changed"
            event["message"] = f"案件状态已变为 {fresh_detail.get('statusName')}（{fresh_status}），未写入 OA"
            with _lock:
                state = _read()
                account = _account(state, session.username)
                _record(account, event)
                _write(state)
            results.append(event)
            continue

        fresh_review = oa.build_approval_review(
            session.base_url, session.token, lawcase_id, fresh_detail
        )
        with _lock:
            state = _read()
            account = _account(state, session.username)
            fresh_decision = _decision(fresh_review, account, lawcase_id)
        if fresh_decision != (action, fingerprint, reasons):
            event["kind"] = "review_changed"
            event["message"] = "审批资料或核验结果在检查期间发生变化，已留待下次重新判断"
            with _lock:
                state = _read()
                account = _account(state, session.username)
                _record(account, event)
                _write(state)
            results.append(event)
            continue

        # Network write intentionally happens outside the state lock, then is read-back verified by oa.py.
        memo = "[办公助手自动审批] " + "；".join(reasons)
        try:
            oa.post_lian_approval(session.base_url, session.token, lawcase_id, action == "approve", memo)
            oa.verify_status_change(session.base_url, session.token, lawcase_id, 3 if action == "approve" else 2)
        except Exception as exc:
            event["kind"] = "action_failed"
            event["message"] = str(exc)
            failures.append(str(exc))
        else:
            event["kind"] = "auto_" + action
            event["message"] = "已写入 OA 并完成回读校验"
            if action == "reject" and fingerprint:
                with _lock:
                    state = _read()
                    account = _account(state, session.username)
                    counts = account.setdefault("reject_counts", {})
                    counts[fingerprint] = int(counts.get(fingerprint, 0)) + 1
                    _write(state)
        with _lock:
            state = _read()
            account = _account(state, session.username)
            _record(account, event)
            _write(state)
        results.append(event)

    with _lock:
        state = _read()
        account = _account(state, session.username)
        account["last_checked_at"] = _now()
        account["last_error"] = failures[-1] if failures else None
        _write(state)
    return {"shadow": shadow, "count": len(results), "results": results}


def _background() -> None:
    while not _stop.wait(POLL_SECONDS):
        try:
            saved = credentials.load_last_login()
        except credentials.CredentialStoreUnavailable:
            # Keep the scheduler alive so a temporarily unavailable vault can
            # recover on a later poll instead of killing the daemon thread.
            continue
        if not saved:
            continue
        session_id: str | None = None
        try:
            restored = sessions.restore(oa.DEFAULT_BASE_URL)
            if restored is None:
                continue
            session_id, session = restored
            if not session.can_approve or not status(session.username)["enabled"]:
                continue
            run_once(session)
        except Exception as exc:
            with _lock:
                state = _read()
                account = _account(state, saved.username)
                account["last_error"] = str(exc)
                _record(account, {"kind": "check_failed", "message": str(exc)})
                _write(state)
        finally:
            # Background restore is ephemeral; retaining its random session id
            # would leak password/token-bearing Session objects every poll.
            sessions.drop(session_id)


def start_scheduler() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_background, name="approval-automation", daemon=True)
    _thread.start()
