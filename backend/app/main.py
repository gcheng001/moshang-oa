"""摩尚OA local backend — FastAPI app.

Serves the REST API for the desktop frontend and, in production, the built
frontend static files. Write operations are limited to filing approval
(approve/reject), always gated and verified by read-back.
"""

from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import assistant, automation, credentials, dialogs, oa, sessions
from .local_server import APP_ID, APP_VERSION

DEFAULT_BASE_URL = os.environ.get("MOSHANG_OA_BASE_URL", oa.DEFAULT_BASE_URL)

app = FastAPI(title="办公助手", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def start_automation_scheduler() -> None:
    automation.start_scheduler()


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"app": APP_ID, "version": APP_VERSION}


def require_session(x_session_id: str | None = Header(default=None)) -> sessions.Session:
    try:
        session = sessions.get(x_session_id)
    except (oa.OAError, requests.RequestException) as exc:
        raise HTTPException(status_code=401, detail=f"会话已失效，请重新登录（{exc}）") from exc
    if session is None:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    return session


def require_approval_session(session: sessions.Session = Depends(require_session)) -> sessions.Session:
    if not session.can_approve:
        raise HTTPException(status_code=403, detail="当前账号无审批权限")
    return session


def oa_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except oa.OAError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"OA 网络请求失败：{exc}") from exc


# ------------------------------------------------------------------- auth


class LoginBody(BaseModel):
    username: str
    password: str
    remember: bool = False
    base_url: str | None = None


def _user_payload(session: sessions.Session) -> dict[str, Any]:
    profile = session.profile
    return {
        "userId": profile.get("userId"),
        "userName": profile.get("userName"),
        "employeeId": profile.get("employeeId"),
        "employeeName": profile.get("employeeName"),
        "lawfirmName": profile.get("lawfirmName"),
        "canApprove": session.can_approve,
    }


@app.get("/api/me")
def api_current_user(session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
    return _user_payload(session)


@app.post("/api/login")
def api_login(body: LoginBody) -> dict[str, Any]:
    base_url = (body.base_url or DEFAULT_BASE_URL).strip()
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(status_code=422, detail="请输入账号和密码")
    try:
        session_id, session = sessions.create(base_url, username, body.password, remember=body.remember)
    except credentials.CredentialStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"无法保持登录：{exc}") from exc
    except oa.OAError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"无法连接 OA：{exc}") from exc
    if not body.remember:
        automation.disable(session.username)
    return {"session_id": session_id, "user": _user_payload(session)}


@app.post("/api/login/restore")
def api_restore_login() -> dict[str, Any]:
    try:
        restored = sessions.restore(DEFAULT_BASE_URL)
    except credentials.CredentialStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"无法读取保持登录信息：{exc}") from exc
    except oa.OAError as exc:
        raise HTTPException(status_code=401, detail=f"保持登录已失效：{exc}") from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"无法连接 OA：{exc}") from exc
    if restored is None:
        raise HTTPException(status_code=401, detail="没有可恢复的登录")
    session_id, session = restored
    return {"session_id": session_id, "user": _user_payload(session)}


@app.post("/api/logout")
def api_logout(x_session_id: str | None = Header(default=None)) -> dict[str, Any]:
    if not x_session_id:
        raise HTTPException(status_code=401, detail="缺少当前会话，无法退出登录")
    try:
        session = sessions.peek(x_session_id)
        if session is not None:
            automation.disable(session.username)
        else:
            saved = credentials.load_last_login()
            if saved is not None:
                automation.disable(saved.username)
        sessions.drop(x_session_id, forget_login=True)
    except credentials.CredentialStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"无法清除保持登录信息：{exc}") from exc
    return {"ok": True}


# ------------------------------------------------------------------ cases


@app.get("/api/cases")
def api_cases(
    keyword: str | None = None,
    status: int | None = None,
    baseTypeId: int | None = None,
    employeeId: int | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    pageIndex: int = 0,
    pageSize: int = 50,
    session: sessions.Session = Depends(require_session),
) -> dict[str, Any]:
    params: dict[str, Any] = {"pageIndex": pageIndex, "pageSize": min(pageSize, 100)}
    if keyword:
        params["keyword"] = keyword
    if status is not None:
        params["status"] = status
    if baseTypeId is not None:
        params["baseTypeId"] = baseTypeId
    if employeeId is not None:
        params["employeeId"] = employeeId
    if startDate:
        params["startDate"] = startDate
    if endDate:
        params["endDate"] = endDate
    payload = oa_call(oa.get_case_list, session.base_url, session.token, params)
    return {"total": payload.get("total") or 0, "rows": payload.get("data") or []}


@app.get("/api/cases/{lawcase_id}")
def api_case_detail(
    lawcase_id: int,
    session: sessions.Session = Depends(require_session),
) -> dict[str, Any]:
    return oa_call(oa.get_case_detail, session.base_url, session.token, lawcase_id)


# ------------------------------------------------------------- documents

_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"|?*\\/]')


def _safe_filename(name: str) -> str:
    return _ILLEGAL_FILENAME_CHARS.sub("", name).strip() or "未命名"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(2, 100):
        candidate = path.with_name(f"{stem}-{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=500, detail=f"同名文件过多，无法保存：{path.name}")


class DocDownloadBody(BaseModel):
    templates: list[str]
    target_dir: str


@app.post("/api/cases/documents/pick-directory")
def api_document_pick_directory(session: sessions.Session = Depends(require_session)) -> dict[str, str | None]:
    directory = dialogs.choose_directory("选择文书保存位置")
    return {"path": str(directory) if directory else None}


@app.get("/api/cases/{lawcase_id}/documents/templates")
def api_case_doc_templates(
    lawcase_id: int,
    session: sessions.Session = Depends(require_session),
) -> dict[str, Any]:
    detail = oa_call(oa.get_case_detail, session.base_url, session.token, lawcase_id)
    templates = oa_call(oa.get_word_templates, session.base_url, session.token, lawcase_id)
    legal_persons, orgs = oa.principal_org_kinds(detail)
    return {
        "case_no": detail.get("no") or detail.get("preNo"),
        "templates": [
            {"name": str(t.get("name") or ""), "isSelected": bool(t.get("isSelected"))}
            for t in templates
            if t.get("name")
        ],
        "principal_legal_persons": legal_persons,
        "principal_orgs": orgs,
    }


@app.post("/api/cases/{lawcase_id}/documents/download")
def api_case_doc_download(
    lawcase_id: int,
    body: DocDownloadBody,
    session: sessions.Session = Depends(require_session),
) -> dict[str, Any]:
    names = [n.strip() for n in body.templates if n.strip()]
    if not names:
        raise HTTPException(status_code=422, detail="请先选择要下载的文书")
    detail = oa_call(oa.get_case_detail, session.base_url, session.token, lawcase_id)
    available = [
        str(t.get("name") or "")
        for t in oa_call(oa.get_word_templates, session.base_url, session.token, lawcase_id)
        if t.get("name")
    ]
    unknown = [n for n in names if n not in available]
    if unknown:
        raise HTTPException(status_code=422, detail=f"以下文书不在本案可用模板列表中：{'、'.join(unknown)}")

    additions, notes = oa.companion_documents(detail, available, names)
    case_no = str(detail.get("no") or detail.get("preNo") or lawcase_id)
    target_dir = Path(body.target_dir).expanduser()
    if not target_dir.is_absolute() or not target_dir.is_dir():
        raise HTTPException(status_code=422, detail="请选择有效的文书保存目录")

    saved: list[dict[str, Any]] = []
    for name in names + additions:
        content, oa_filename = oa_call(
            oa.export_word_template, session.base_url, session.token, lawcase_id, name
        )
        if not content:
            raise HTTPException(status_code=502, detail=f"《{name}》导出成功但下载内容为空，请重试")
        filename = _safe_filename(oa_filename or f"{case_no}-{name}.docx")
        if not Path(filename).suffix:
            filename += ".docx"
        path = _unique_path(target_dir / filename)
        path.write_bytes(content)
        saved.append(
            {
                "template": name,
                "path": str(path),
                "size": len(content),
                "valid_docx": zipfile.is_zipfile(path),
                "auto_added": name in additions,
            }
        )
    return {"ok": True, "case_no": case_no, "dir": str(target_dir), "saved": saved, "notes": notes}


# -------------------------------------------------------------- approvals


@app.get("/api/approvals/pending")
def api_pending(session: sessions.Session = Depends(require_approval_session)) -> dict[str, Any]:
    filing = oa_call(
        oa.get_case_list, session.base_url, session.token, {"status": 1, "pageIndex": 0, "pageSize": 100}
    )
    closing = oa_call(
        oa.get_case_list, session.base_url, session.token, {"status": 4, "pageIndex": 0, "pageSize": 100}
    )
    return {
        "filing": filing.get("data") or [],
        "closing": closing.get("data") or [],
    }


@app.get("/api/approvals/{lawcase_id}/check")
def api_approval_check(
    lawcase_id: int,
    session: sessions.Session = Depends(require_approval_session),
) -> dict[str, Any]:
    detail = oa_call(oa.get_case_detail, session.base_url, session.token, lawcase_id)
    review = oa_call(oa.build_approval_review, session.base_url, session.token, lawcase_id, detail)
    review["gate_errors"] = oa.approval_gate_errors(review)
    review["detail"] = detail
    return review


class ApproveBody(BaseModel):
    memo: str = ""
    conflict_reviewed: bool = False
    conflict_memo: str = ""
    risk_reviewed: bool = False
    risk_memo: str = ""


class RejectBody(BaseModel):
    memo: str


class AutomationBody(BaseModel):
    enabled: bool


@app.get("/api/approvals/automation")
def api_automation_status(
    session: sessions.Session = Depends(require_approval_session),
) -> dict[str, Any]:
    return automation.status(session.username)


@app.post("/api/approvals/automation")
def api_automation_set(
    body: AutomationBody,
    session: sessions.Session = Depends(require_approval_session),
) -> dict[str, Any]:
    try:
        return automation.set_enabled(session, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/approvals/automation/check-now")
def api_automation_check_now(
    session: sessions.Session = Depends(require_approval_session),
) -> dict[str, Any]:
    try:
        return automation.run_once(session)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/approvals/{lawcase_id}/approve")
def api_approve(
    lawcase_id: int,
    body: ApproveBody,
    session: sessions.Session = Depends(require_approval_session),
) -> dict[str, Any]:
    detail = oa_call(oa.get_case_detail, session.base_url, session.token, lawcase_id)
    old_status = oa.row_status(detail)
    if old_status != 1:
        raise HTTPException(
            status_code=409,
            detail=f"该案件当前状态为 {detail.get('statusName')}（{old_status}），不是立案待审，无法审批",
        )

    review = oa_call(oa.build_approval_review, session.base_url, session.token, lawcase_id, detail)
    gate_errors = oa.approval_gate_errors(
        review,
        conflict_reviewed=body.conflict_reviewed,
        conflict_memo=body.conflict_memo,
        risk_reviewed=body.risk_reviewed,
    )
    if gate_errors:
        raise HTTPException(status_code=409, detail={"gate_errors": gate_errors})

    memo = body.memo.strip()
    if body.conflict_memo.strip():
        memo = f"{memo}\n利冲复核：{body.conflict_memo.strip()}".strip()
    if body.risk_memo.strip():
        memo = f"{memo}\n风险收费复核：{body.risk_memo.strip()}".strip()

    fresh = oa_call(oa.get_case_detail, session.base_url, session.token, lawcase_id)
    fresh_status = oa.row_status(fresh)
    if fresh_status != 1:
        raise HTTPException(
            status_code=409,
            detail=f"审批前案件状态已变为 {fresh.get('statusName')}（{fresh_status}），本次未写入",
        )
    fresh_review = oa_call(
        oa.build_approval_review, session.base_url, session.token, lawcase_id, fresh
    )
    fresh_gate_errors = oa.approval_gate_errors(
        fresh_review,
        conflict_reviewed=body.conflict_reviewed,
        conflict_memo=body.conflict_memo,
        risk_reviewed=body.risk_reviewed,
    )
    if fresh_gate_errors:
        raise HTTPException(status_code=409, detail={"gate_errors": fresh_gate_errors})
    oa_call(oa.post_lian_approval, session.base_url, session.token, lawcase_id, True, memo)
    after = oa_call(oa.verify_status_change, session.base_url, session.token, lawcase_id, 3)
    return {
        "ok": True,
        "action": "approve",
        "lawcase_id": lawcase_id,
        "case_no": after.get("no") or after.get("preNo"),
        "new_status": after.get("status"),
        "new_status_name": after.get("statusName"),
    }


@app.post("/api/approvals/{lawcase_id}/reject")
def api_reject(
    lawcase_id: int,
    body: RejectBody,
    session: sessions.Session = Depends(require_approval_session),
) -> dict[str, Any]:
    memo = body.memo.strip()
    if not memo:
        raise HTTPException(status_code=422, detail="驳回必须填写审批意见")
    detail = oa_call(oa.get_case_detail, session.base_url, session.token, lawcase_id)
    old_status = oa.row_status(detail)
    if old_status != 1:
        raise HTTPException(
            status_code=409,
            detail=f"该案件当前状态为 {detail.get('statusName')}（{old_status}），不是立案待审，无法驳回",
        )
    oa_call(oa.post_lian_approval, session.base_url, session.token, lawcase_id, False, memo)
    after = oa_call(oa.verify_status_change, session.base_url, session.token, lawcase_id, 2)
    return {
        "ok": True,
        "action": "reject",
        "lawcase_id": lawcase_id,
        "case_no": after.get("no") or after.get("preNo"),
        "new_status": after.get("status"),
        "new_status_name": after.get("statusName"),
    }


# ------------------------------------------------------------ 办案助手（本机能力，不触碰 OA）


class PickBody(BaseModel):
    mode: str = "files"  # files | folder


class ConvertBody(BaseModel):
    paths: list[str]
    engine: str = "mineru"


class WechatBody(BaseModel):
    paths: list[str]
    interval: float = 1.0
    smart_filter: bool = False
    preserve_head_sec: float = 8.0


class OrganizeBody(BaseModel):
    source: str = "ocr"  # ocr | wechat | custom
    dir: str | None = None


class RevealBody(BaseModel):
    path: str


@app.get("/api/assistant/overview")
def api_assistant_overview(session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
    return assistant.tool_status()


@app.post("/api/assistant/pick")
def api_assistant_pick(body: PickBody, session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
    return {"paths": assistant.pick_paths(body.mode)}


@app.post("/api/assistant/convert")
def api_assistant_convert(body: ConvertBody, session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
    if not body.paths:
        raise HTTPException(status_code=422, detail="请先选择文件")
    if body.engine not in assistant.ENGINES:
        raise HTTPException(status_code=422, detail=f"未知引擎：{body.engine}")
    return assistant.start_convert(body.paths, body.engine)


@app.post("/api/assistant/wechat")
def api_assistant_wechat(body: WechatBody, session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
    if not body.paths:
        raise HTTPException(status_code=422, detail="请先选择录屏视频")
    if not (0.2 <= body.interval <= 60):
        raise HTTPException(status_code=422, detail="截图间隔须在 0.2~60 秒之间")
    return assistant.start_wechat(body.paths, body.interval, body.smart_filter, body.preserve_head_sec)


@app.post("/api/assistant/organize")
def api_assistant_organize(body: OrganizeBody, session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
    if body.source == "custom" and not (body.dir or "").strip():
        raise HTTPException(status_code=422, detail="请选择要整理的目录")
    return assistant.start_organize(body.source, body.dir)


@app.get("/api/assistant/jobs")
def api_assistant_jobs(session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
    return {"jobs": assistant.list_jobs()}


@app.get("/api/assistant/jobs/{job_id}")
def api_assistant_job(job_id: str, session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
    job = assistant.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.post("/api/assistant/reveal")
def api_assistant_reveal(body: RevealBody, session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
    if not assistant.reveal(body.path):
        raise HTTPException(status_code=404, detail="文件或目录不存在")
    return {"ok": True}


# ------------------------------------------------------------- static SPA

if getattr(sys, "frozen", False):
    # PyInstaller places explicitly bundled frontend assets next to the
    # extracted application modules, not three source-tree levels above them.
    _DIST = Path(sys._MEIPASS) / "frontend" / "dist"  # type: ignore[attr-defined]
else:
    _DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        target = _DIST / path
        if path and target.is_file():
            return FileResponse(target)
        # index.html 禁缓存：WKWebView（private_mode=False 持久化）曾缓存旧入口页，
        # 导致重新打包后窗口仍渲染旧界面；资源文件带内容哈希可正常缓存
        return FileResponse(_DIST / "index.html", headers={"Cache-Control": "no-store"})
