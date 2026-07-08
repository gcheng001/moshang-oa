"""摩尚OA local backend — FastAPI app.

Serves the REST API for the desktop frontend and, in production, the built
frontend static files. Write operations are limited to filing approval
(approve/reject), always gated and verified by read-back.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import assistant, oa, sessions

DEFAULT_BASE_URL = os.environ.get("MOSHANG_OA_BASE_URL", oa.DEFAULT_BASE_URL)

app = FastAPI(title="摩尚OA", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_session(x_session_id: str | None = Header(default=None)) -> sessions.Session:
    try:
        session = sessions.get(x_session_id)
    except (oa.OAError, requests.RequestException) as exc:
        raise HTTPException(status_code=401, detail=f"会话已失效，请重新登录（{exc}）") from exc
    if session is None:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
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
    apikey: str
    base_url: str | None = None


@app.post("/api/login")
def api_login(body: LoginBody) -> dict[str, Any]:
    base_url = (body.base_url or DEFAULT_BASE_URL).strip()
    apikey = body.apikey.strip()
    if not apikey:
        raise HTTPException(status_code=422, detail="请输入 API Key")
    try:
        session_id, session = sessions.create(base_url, apikey)
    except oa.OAError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"无法连接 OA：{exc}") from exc
    profile = session.profile
    return {
        "session_id": session_id,
        "user": {
            "userId": profile.get("userId"),
            "userName": profile.get("userName"),
            "employeeId": profile.get("employeeId"),
            "employeeName": profile.get("employeeName"),
            "lawfirmName": profile.get("lawfirmName"),
        },
    }


@app.post("/api/logout")
def api_logout(x_session_id: str | None = Header(default=None)) -> dict[str, Any]:
    sessions.drop(x_session_id)
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


# -------------------------------------------------------------- approvals


@app.get("/api/approvals/pending")
def api_pending(session: sessions.Session = Depends(require_session)) -> dict[str, Any]:
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
    session: sessions.Session = Depends(require_session),
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


@app.post("/api/approvals/{lawcase_id}/approve")
def api_approve(
    lawcase_id: int,
    body: ApproveBody,
    session: sessions.Session = Depends(require_session),
) -> dict[str, Any]:
    detail = oa_call(oa.get_case_detail, session.base_url, session.token, lawcase_id)
    old_status = int(detail.get("status") or -99)
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
    session: sessions.Session = Depends(require_session),
) -> dict[str, Any]:
    memo = body.memo.strip()
    if not memo:
        raise HTTPException(status_code=422, detail="驳回必须填写审批意见")
    detail = oa_call(oa.get_case_detail, session.base_url, session.token, lawcase_id)
    old_status = int(detail.get("status") or -99)
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

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        target = _DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(_DIST / "index.html")
