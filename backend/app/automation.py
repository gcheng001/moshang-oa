"""Account-bound, auditable automatic filing approval.

Only status=1 filing applications are handled. Business-rule failures are
rejected with complete reasons; transport/read failures never cause rejection
and are retried on the next three-minute poll.
"""

from __future__ import annotations

import json
import platform
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import credentials, notifications, oa, sessions

POLL_SECONDS = 3 * 60
GRACE_SECONDS = 2 * 60
TECHNICAL_ALERT_THRESHOLD = 3
RULE_VERSION = "2026.08.20-v1"
STATE_DIR = Path.home() / ".office-assistant"
STATE_FILE = STATE_DIR / "approval-automation.json"

_lock = threading.RLock()
_run_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict[str, Any]:
    return {"version": 2, "accounts": {}}


def _read() -> dict[str, Any]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("accounts"), dict) else _default_state()
    except (FileNotFoundError, OSError, json.JSONDecodeError):
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
    value = state.setdefault("accounts", {}).setdefault(username, {})
    value.setdefault("enabled", False)
    value.setdefault("paused", False)
    value.setdefault("last_checked_at", None)
    value.setdefault("last_error", None)
    value.setdefault("events", [])
    value.setdefault("first_seen", {})
    value.setdefault("manual_pending", {})
    value.setdefault("consecutive_failures", 0)
    value.setdefault("technical_alert_open", False)
    return value


def _events(account: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
    events = account.get("events") or []
    return events[-limit:] if isinstance(events, list) else []


def _record(account: dict[str, Any], event: dict[str, Any]) -> None:
    account.setdefault("events", []).append({"at": _now(), **event})
    del account["events"][:-500]


def _manual_reason_fingerprint(reasons: list[str]) -> str:
    normalized = sorted({str(reason).strip() for reason in reasons if str(reason).strip()})
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _device() -> dict[str, str]:
    return {
        "device_id": f"{uuid.getnode():012x}",
        "device_name": socket.gethostname(),
        "platform": platform.system(),
    }


def status(username: str) -> dict[str, Any]:
    with _lock:
        account = _account(_read(), username)
        return {
            "enabled": bool(account.get("enabled")),
            "paused": bool(account.get("paused")),
            "mode": "active",
            "shadow_remaining_seconds": 0,
            "poll_minutes": POLL_SECONDS // 60,
            "grace_seconds": GRACE_SECONDS,
            "rule_version": RULE_VERSION,
            "consecutive_failures": int(account.get("consecutive_failures") or 0),
            "last_checked_at": account.get("last_checked_at"),
            "last_error": account.get("last_error"),
            "events": list(reversed(_events(account, 30))),
            **_device(),
        }


def record_event(username: str, event: dict[str, Any]) -> None:
    with _lock:
        state = _read()
        account = _account(state, username)
        _record(account, {**_device(), **event})
        _write(state)


def history(username: str, limit: int = 500) -> list[dict[str, Any]]:
    with _lock:
        return list(reversed(_events(_account(_read(), username), limit)))


def set_enabled(session: sessions.Session, enabled: bool) -> dict[str, Any]:
    if enabled and not credentials.has_password(session.username):
        raise ValueError("请先勾选“保持登录”，自动审批才能在电脑后台持续运行")
    with _lock:
        state = _read()
        account = _account(state, session.username)
        account["enabled"] = bool(enabled)
        account["paused"] = False if enabled else account.get("paused", False)
        account["last_error"] = None
        _record(
            account,
            {
                **_device(),
                "kind": "automation_enabled" if enabled else "automation_disabled",
                "message": "已开启自动审批：每3分钟检查，业务异常自动驳回" if enabled else "已关闭自动审批",
                "rule_version": RULE_VERSION,
            },
        )
        _write(state)
    return status(session.username)


def set_paused(session: sessions.Session, paused: bool) -> dict[str, Any]:
    with _lock:
        state = _read()
        account = _account(state, session.username)
        if not account.get("enabled"):
            raise ValueError("自动审批尚未开启")
        account["paused"] = bool(paused)
        _record(
            account,
            {
                **_device(),
                "kind": "automation_paused" if paused else "automation_resumed",
                "message": "已紧急暂停，保留值守但不写入 OA" if paused else "已恢复自动审批",
            },
        )
        _write(state)
    return status(session.username)


def disable(username: str) -> None:
    with _lock:
        state = _read()
        account = _account(state, username)
        if account.get("enabled"):
            account["enabled"] = False
            _record(account, {**_device(), "kind": "automation_disabled", "message": "已关闭自动审批"})
        _write(state)


def _decision(review: dict[str, Any], *_args: Any) -> tuple[str, str, list[str]]:
    technical = oa.approval_technical_errors(review)
    if technical:
        return "technical_error", "", technical
    hard = list(dict.fromkeys(oa.approval_hard_errors(review)))
    if hard:
        return "reject", "", hard
    manual_items = oa.approval_manual_review_items(review)
    if manual_items:
        return "manual_review", "", [item["summary"] for item in manual_items]
    return "approve", "", ["全部适用的自动审批规则通过"]


def _submitted_at(row: dict[str, Any], detail: dict[str, Any]) -> str | None:
    for source in (detail, row):
        for key in ("submitTime", "approvalSubmitTime", "createTime", "shouliDate"):
            value = source.get(key)
            if value:
                return str(value)
    return None


def _notify_safely(message: str) -> None:
    try:
        notifications.send_feishu(message)
    except Exception:
        pass


def _clear_case_tracking(username: str, case_key: str) -> None:
    with _lock:
        state = _read()
        account = _account(state, username)
        account.setdefault("first_seen", {}).pop(case_key, None)
        account.setdefault("manual_pending", {}).pop(case_key, None)
        _write(state)


def run_once(session: sessions.Session) -> dict[str, Any]:
    if not _run_lock.acquire(blocking=False):
        raise ValueError("自动审批检查正在进行，请稍后再试")
    try:
        return _run_once(session)
    finally:
        _run_lock.release()


def _run_once(session: sessions.Session) -> dict[str, Any]:
    with _lock:
        account = _account(_read(), session.username)
        if not account.get("enabled"):
            raise ValueError("自动审批尚未开启")
        if account.get("paused"):
            raise ValueError("自动审批已紧急暂停")

    rows: list[dict[str, Any]] = []
    page_index = 0
    while True:
        payload = oa.get_case_list(
            session.base_url, session.token, {"status": 1, "pageIndex": page_index, "pageSize": 100}
        )
        batch = [row for row in payload.get("data") or [] if isinstance(row, dict)]
        rows.extend(batch)
        total = int(payload.get("total") or 0)
        if len(batch) < 100 or (total and len(rows) >= total):
            break
        page_index += 1

    pending_ids = {str(oa.row_case_id(row)) for row in rows if oa.row_case_id(row)}
    with _lock:
        state = _read()
        account = _account(state, session.username)
        first_seen = account.setdefault("first_seen", {})
        for stale in set(first_seen) - pending_ids:
            first_seen.pop(stale, None)
        manual_pending = account.setdefault("manual_pending", {})
        for stale in set(manual_pending) - pending_ids:
            manual_pending.pop(stale, None)
        _write(state)

    results: list[dict[str, Any]] = []
    technical_failures: list[str] = []
    for row in rows:
        lawcase_id = oa.row_case_id(row)
        if not lawcase_id:
            continue
        case_key = str(lawcase_id)
        with _lock:
            state = _read()
            account = _account(state, session.username)
            first_seen = account.setdefault("first_seen", {})
            seen = first_seen.get(case_key)
            if not seen:
                seen = {"at": _now(), "epoch": time.time()}
                first_seen[case_key] = seen
                event = {
                    **_device(), "kind": "waiting_reread", "case_id": lawcase_id,
                    "case_no": row.get("no") or row.get("preNo"),
                    "oa_submitted_at": _submitted_at(row, row), "first_seen_at": seen["at"],
                    "message": "已发现待审申请，等待2分钟后重新读取再审批",
                }
                _record(account, event)
                _write(state)
                results.append(event)
                continue
            if time.time() - float(seen.get("epoch") or 0) < GRACE_SECONDS:
                continue

        started = time.monotonic()
        event: dict[str, Any] = {
            **_device(), "case_id": lawcase_id, "case_no": row.get("no") or row.get("preNo"),
            "oa_submitted_at": _submitted_at(row, row), "first_seen_at": seen.get("at"),
            "rule_version": RULE_VERSION,
        }
        try:
            detail = oa.get_case_detail(session.base_url, session.token, lawcase_id)
            if oa.row_status(detail) != 1:
                event.update(kind="status_changed", message="案件已不再是立案待审，本次未写入 OA")
                _clear_case_tracking(session.username, case_key)
                results.append(event)
                record_event(session.username, event)
                continue
            event["case_no"] = detail.get("no") or detail.get("preNo") or str(lawcase_id)
            event["oa_submitted_at"] = _submitted_at(row, detail)
            review = oa.build_approval_review(session.base_url, session.token, lawcase_id, detail)
            action, _, reasons = _decision(review)
        except Exception as exc:
            reason = str(exc)
            technical_failures.append(reason)
            event.update(kind="technical_retry", reasons=[reason], message="技术异常，未驳回；下轮自动重试")
            record_event(session.username, event)
            results.append(event)
            continue

        if action == "technical_error":
            technical_failures.extend(reasons)
            event.update(kind="technical_retry", reasons=reasons, message="技术异常，未驳回；下轮自动重试")
            record_event(session.username, event)
            results.append(event)
            continue

        with _lock:
            account = _account(_read(), session.username)
            if not account.get("enabled") or account.get("paused"):
                event.update(kind="automation_stopped", message="自动审批已关闭或暂停，本次未写入 OA")
                record_event(session.username, event)
                results.append(event)
                break

        try:
            fresh = oa.get_case_detail(session.base_url, session.token, lawcase_id)
            if oa.row_status(fresh) != 1:
                event.update(kind="status_changed", message="写入前状态已变化，本次未写入 OA")
                _clear_case_tracking(session.username, case_key)
                record_event(session.username, event)
                results.append(event)
                continue
            fresh_review = oa.build_approval_review(session.base_url, session.token, lawcase_id, fresh)
            fresh_action, _, fresh_reasons = _decision(fresh_review)
            if (fresh_action, fresh_reasons) != (action, reasons):
                event.update(kind="review_changed", message="资料在复核期间发生变化，下轮重新判断")
                record_event(session.username, event)
                results.append(event)
                continue
            if action == "manual_review":
                fingerprint = _manual_reason_fingerprint(reasons)
                completed_at = _now()
                event.update(
                    kind="manual_review",
                    action="manual_review",
                    reasons=reasons,
                    message="需人工复核，本次未写入 OA；请合伙人在「审批记录」中处理",
                    decision_started_at=event.get("first_seen_at"),
                    approval_time=completed_at,
                    decision_completed_at=completed_at,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
                with _lock:
                    state = _read()
                    account = _account(state, session.username)
                    manual_pending = account.setdefault("manual_pending", {})
                    previous = manual_pending.get(case_key) or {}
                    if previous.get("fingerprint") == fingerprint:
                        _write(state)
                        continue
                    manual_pending[case_key] = {
                        "fingerprint": fingerprint,
                        "reasons": reasons,
                        "updated_at": completed_at,
                    }
                    _record(account, event)
                    _write(state)
                _notify_safely(f"办公助手转人工：{event['case_no']}\n" + "\n".join(reasons))
                results.append(event)
                continue
            numbered = "；".join(f"{index + 1}. {reason}" for index, reason in enumerate(reasons))
            memo = f"[办公助手自动审批][规则 {RULE_VERSION}] {numbered}"
            oa.post_lian_approval(session.base_url, session.token, lawcase_id, action == "approve", memo)
            after = oa.verify_status_change(session.base_url, session.token, lawcase_id, 3 if action == "approve" else 2)
        except Exception as exc:
            reason = str(exc)
            technical_failures.append(reason)
            event.update(kind="action_failed", reasons=[reason], message="OA 写入或回读失败，下轮自动重试")
        else:
            completed_at = _now()
            event.update(
                kind="auto_" + action,
                action=action,
                reasons=reasons,
                message="已写入 OA 并完成回读校验",
                decision_started_at=event.get("first_seen_at"),
                approval_time=completed_at,
                decision_completed_at=completed_at,
                duration_ms=int((time.monotonic() - started) * 1000),
                new_status=after.get("status"),
                new_status_name=after.get("statusName"),
            )
            _clear_case_tracking(session.username, case_key)
            _notify_safely(f"办公助手自动{'通过' if action == 'approve' else '驳回'}：{event['case_no']}\n{numbered}")
        record_event(session.username, event)
        results.append(event)

    with _lock:
        state = _read()
        account = _account(state, session.username)
        account["last_checked_at"] = _now()
        if technical_failures:
            account["consecutive_failures"] = int(account.get("consecutive_failures") or 0) + 1
            account["last_error"] = technical_failures[-1]
            if account["consecutive_failures"] >= TECHNICAL_ALERT_THRESHOLD and not account.get("technical_alert_open"):
                account["technical_alert_open"] = True
                _notify_safely(f"办公助手连续 {account['consecutive_failures']} 轮出现技术异常，未对异常案件作出审批或驳回，请检查网络或 OA。")
        else:
            if account.get("technical_alert_open"):
                _notify_safely("办公助手自动审批技术异常已恢复。")
            account["consecutive_failures"] = 0
            account["technical_alert_open"] = False
            account["last_error"] = None
        _write(state)
    return {"shadow": False, "count": len(results), "results": results}


def _background() -> None:
    while not _stop.wait(POLL_SECONDS):
        try:
            saved = credentials.load_last_login()
        except credentials.CredentialStoreUnavailable:
            continue
        if not saved:
            continue
        session_id: str | None = None
        try:
            restored = sessions.restore(oa.DEFAULT_BASE_URL)
            if restored is None:
                continue
            session_id, session = restored
            state = status(session.username)
            if session.can_approve and state["enabled"] and not state["paused"]:
                run_once(session)
        except Exception as exc:
            with _lock:
                state_data = _read()
                account = _account(state_data, saved.username)
                account["consecutive_failures"] = int(account.get("consecutive_failures") or 0) + 1
                account["last_error"] = str(exc)
                _record(account, {"kind": "check_failed", "message": str(exc), **_device()})
                should_alert = (
                    account["consecutive_failures"] >= TECHNICAL_ALERT_THRESHOLD
                    and not account.get("technical_alert_open")
                )
                if should_alert:
                    account["technical_alert_open"] = True
                _write(state_data)
            if should_alert:
                _notify_safely(
                    f"办公助手连续 {account['consecutive_failures']} 轮无法完成待审扫描，未对案件作出审批或驳回：{exc}"
                )
        finally:
            sessions.drop(session_id)


def start_scheduler() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_background, name="approval-automation", daemon=True)
    _thread.start()
