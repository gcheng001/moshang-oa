"""摩尚OA client — ported from the verified skill script oa_probe.py.

All read paths (login, case list/detail, approval checks) are side-effect free.
The only write path is Lianshenpi (filing approval), guarded by the compliance
gate and followed by a read-back verification.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import unquote, urljoin

import requests

DEFAULT_BASE_URL = "https://moshang2.ycq6.com"

# 利冲严重度用：案件仍处于活动/待定状态（-2撤销被驳回、-1撤销审核中、0草稿、
# 1立案待审、3办理中、4结案待审、5结案未通过均视为在办）
ACTIVE_CASE_STATUSES = {-2, -1, 0, 1, 3, 4, 5}
# 重复立案硬阻断用：仅在办/待处理状态。2「立案未通过」不算——驳回后重新申报
# 不应被旧记录永久阻断，降级为人工复核提示
ACTIVE_DUPLICATE_STATUSES = {1, 3, 4, 5}
RISK_CHARGE_METHOD_ID = 5
RISK_PROHIBITED_KEYWORDS = (
    "刑事",
    "行政诉讼",
    "国家赔偿",
    "群体性诉讼",
    "婚姻",
    "离婚",
    "继承",
    "社会保险",
    "最低生活保障",
    "赡养费",
    "抚养费",
    "扶养费",
    "抚恤金",
    "救济金",
    "工伤赔偿",
    "劳动报酬",
)
RISK_FEE_TIERS = (
    (Decimal("1000000"), Decimal("0.18")),
    (Decimal("4000000"), Decimal("0.15")),
    (Decimal("5000000"), Decimal("0.12")),
    (Decimal("40000000"), Decimal("0.09")),
    (None, Decimal("0.06")),
)


class OAError(RuntimeError):
    """Raised when the OA returns an error envelope or unexpected shape."""


# ---------------------------------------------------------------- transport

# OA 是国内直连站点，本机常驻代理（如 127.0.0.1:7897）会掐断其 TLS 握手（SSL EOF）；
# APP 可能从带 https_proxy 环境变量的 shell 被拉起——OA 请求一律直连，忽略代理环境。
_http = requests.Session()
_http.trust_env = False


def login(base_url: str, api_key: str) -> str:
    url = urljoin(base_url.rstrip("/") + "/", "DataServices/AgentAPI/Login")
    resp = _http.get(url, params={"apikey": api_key}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    token = ((data or {}).get("data") or {}).get("token")
    if not token:
        raise OAError(f"登录失败：OA 未返回 token（{data.get('msg') or data}）")
    return token


def login_with_password(base_url: str, username: str, password: str) -> tuple[str, dict[str, Any]]:
    """Use the OA web login endpoint and request a token for local API calls."""
    url = urljoin(base_url.rstrip("/") + "/", "Account/Login")
    resp = _http.post(
        url,
        data={
            "userName": username,
            "password": password,
            "ajax": "true",
            "app": "Default",
            "forAccessToken": "true",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    token = (data or {}).get("AccessToken")
    if not token:
        raise OAError(str((data or {}).get("LoginFailedMessage") or "账号或密码不正确"))
    return str(token), data if isinstance(data, dict) else {}


def get_login_info(base_url: str, token: str) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", "Account/GetLoginInfo")
    resp = _http.get(url, headers={"nedev_access_token": token}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise OAError(f"Account/GetLoginInfo 返回异常：{data!r}")
    return data


def has_filing_approval_permission(login_info: dict[str, Any]) -> bool:
    """Mirror the live LawcaseList.page InitiateApprove menu authorization."""
    if login_info.get("IsAdmin") is True:
        return True
    permissions = login_info.get("MenuPermissions") or {}
    keys = permissions.keys() if isinstance(permissions, dict) else permissions
    return "LawcaseList1" in keys


def agent_get(base_url: str, token: str, action: str, params: dict[str, Any] | None = None) -> Any:
    url = urljoin(base_url.rstrip("/") + "/", f"DataServices/AgentAPI/{action}")
    resp = _http.get(url, headers={"nedev_access_token": token}, params=params or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def post_form(base_url: str, token: str, path: str, form: dict[str, str]) -> Any:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    resp = _http.post(url, headers={"nedev_access_token": token}, data=form, timeout=30)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"text": resp.text}


def response_data(result: Any) -> Any:
    if isinstance(result, dict):
        code = result.get("code")
        if code == 200 and "data" in result:
            return result["data"]
        if code is not None and code != 200:
            raise OAError(str(result.get("msg") or f"OA 返回 code={code}"))
    return result


# ---------------------------------------------------------------- helpers


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).casefold()


def split_names(value: Any) -> list[str]:
    if not value:
        return []
    values = value if isinstance(value, list) else re.split(r"[、,，;；/\n]+", str(value))
    return [name.strip() for name in values if str(name).strip()]


def decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


# 收费文本金额提取：取带货币标记的金额（元/块 结尾、¥/￥ 开头、或 万/千 单位），排除费率百分比
_ARABIC_AMOUNT = re.compile(
    r"[￥¥]\s*([0-9][0-9,，]*(?:\.[0-9]+)?)\s*(万|千)?"
    r"|([0-9][0-9,，]*(?:\.[0-9]+)?)\s*(万|千)?\s*(?:元|块)"
)
_BARE_UNIT_AMOUNT = re.compile(r"([0-9][0-9,，]*(?:\.[0-9]+)?)\s*(万|千)(?![分克米瓦])")
_CN_AMOUNT = re.compile(r"([零一二两三四五六七八九十百千万亿]{1,12})\s*(?:元|块)")
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}
# 金额前若紧跟这些语境词，视为标的/损失等案值而非收费，不参与比对
_NON_FEE_CONTEXT = ("标的", "赔偿", "争议", "损失", "涉案", "欠款", "借款", "货款", "本金", "利息")


def _cn_numeral_to_decimal(text: str) -> Decimal | None:
    total, section, digit = 0, 0, 0
    for ch in text:
        if ch in _CN_DIGITS:
            digit = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            if unit >= 10000:
                total = (total + section + digit) * unit
                section, digit = 0, 0
            else:
                section += (digit or 1) * unit
                digit = 0
        else:
            return None
    result = total + section + digit
    return Decimal(result) if result > 0 else None


def extract_fee_amounts(text: str) -> list[Decimal]:
    """从收费方案/收费说明文本中提取疑似收费金额。

    按文本位置去重（同一处文字只计一次），保留重复金额以支持分期合计比对。
    """
    text = text or ""
    found: list[tuple[int, int, Decimal]] = []

    def add(start: int, end: int, value: Decimal | None) -> None:
        if value is None or value <= 0:
            return
        prefix = text[max(0, start - 8) : start]
        if any(kw in prefix for kw in _NON_FEE_CONTEXT):
            return
        if any(start < e and end > s for s, e, _ in found):
            return
        found.append((start, end, value))

    for match in _ARABIC_AMOUNT.finditer(text):
        number = match.group(1) or match.group(3)
        unit = match.group(2) if match.group(1) else match.group(4)
        value = decimal_value(number.replace(",", "").replace("，", ""))
        if value is not None and unit:
            value *= {"万": 10000, "千": 1000}[unit]
        add(match.start(), match.end(), value)
    for match in _BARE_UNIT_AMOUNT.finditer(text):
        value = decimal_value(match.group(1).replace(",", "").replace("，", ""))
        if value is not None:
            value *= {"万": 10000, "千": 1000}[match.group(2)]
        add(match.start(), match.end(), value)
    for match in _CN_AMOUNT.finditer(text):
        add(match.start(), match.end(), _cn_numeral_to_decimal(match.group(1)))

    return [value for _, _, value in sorted(found, key=lambda item: item[0])]


def fee_amounts_match(registered: Decimal, scheme_amounts: list[Decimal]) -> bool:
    """登记收费与方案金额是否可对上：等于其中某笔，或等于各笔合计。"""
    return not scheme_amounts or registered in scheme_amounts or registered == sum(scheme_amounts)


def format_amounts(amounts: list[Decimal]) -> str:
    return "、".join(f"{a:,.0f} 元" for a in amounts)


def risk_fee_cap(subject_amount: Any) -> Decimal | None:
    """Graduated maximum fee under 司发通〔2021〕87号第六项."""
    amount = decimal_value(subject_amount)
    if amount is None or amount <= 0:
        return None
    remaining = amount
    cap = Decimal("0")
    for width, rate in RISK_FEE_TIERS:
        portion = remaining if width is None else min(remaining, width)
        cap += portion * rate
        remaining -= portion
        if remaining <= 0:
            break
    return cap.quantize(Decimal("0.01"))


# ---------------------------------------------------------------- queries


def get_profile(base_url: str, token: str) -> dict[str, Any]:
    result = response_data(agent_get(base_url, token, "GetAgentProfile"))
    if not isinstance(result, dict):
        raise OAError(f"GetAgentProfile 返回异常：{result!r}")
    return result


def get_case_list(base_url: str, token: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = response_data(agent_get(base_url, token, "GetLawcases", params))
    if not isinstance(payload, dict):
        raise OAError(f"GetLawcases 返回异常：{payload!r}")
    return payload


def get_case_list_all(base_url: str, token: str, keyword: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_index = 0
    while True:
        payload = get_case_list(
            base_url, token, {"keyword": keyword, "pageIndex": page_index, "pageSize": 100}
        )
        page = payload.get("data") or []
        rows.extend(row for row in page if isinstance(row, dict))
        if not page or len(rows) >= int(payload.get("total") or 0):
            return rows
        page_index += 1


def get_case_detail(base_url: str, token: str, lawcase_id: int) -> dict[str, Any]:
    result = response_data(agent_get(base_url, token, "GetLawcaseDetail", {"lawcaseId": lawcase_id}))
    if not isinstance(result, dict):
        raise OAError(f"GetLawcaseDetail 返回异常：{result!r}")
    return result


def get_case_entity(base_url: str, token: str, lawcase_id: int, detail: dict[str, Any]) -> dict[str, Any]:
    owners = ["Page:LawcaseDetails_刑事@1"] if is_criminal_case(detail) else ["Page:LawcaseDetails_民事@1"]
    result = post_form(
        base_url,
        token,
        "/DataService/GetEntity",
        {
            "entityType": "ApplicationData.Lawcase",
            "entityKeys": json.dumps([lawcase_id]),
            "owners": json.dumps(owners, ensure_ascii=False),
        },
    )
    value = result.get("Value") if isinstance(result, dict) else None
    return value if isinstance(value, dict) else {}


def party_names(detail: dict[str, Any]) -> tuple[list[str], list[str]]:
    clients = [row for row in (detail.get("clients") or []) if isinstance(row, dict)]
    principals = [str(row.get("name") or "").strip() for row in clients if row.get("roleType") == 0]
    opponents = [str(row.get("name") or "").strip() for row in clients if row.get("roleType") == 1]
    return (
        [n for n in principals if n] or split_names(detail.get("wtrNames") or detail.get("dsrNames")),
        [n for n in opponents if n] or split_names(detail.get("tosNames")),
    )


def row_case_id(row: dict[str, Any]) -> int:
    try:
        return int(row.get("id") or row.get("lawcaseId") or 0)
    except (TypeError, ValueError):
        return 0


def row_status(row: dict[str, Any]) -> int | None:
    try:
        return int(row.get("status"))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------- case head dictionary
# OA 自带案由/罪名字典（GetCaseHeads 无参返回全量 12 棵树约 2009 节点，2026-07-10 实测；
# 早前 skill 记录「民事细分为空」已过时）。立案审批要求案由必须命中本字典。

CASE_HEADS_TTL_SECONDS = 12 * 3600
_case_heads_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def get_case_heads(base_url: str, token: str) -> list[dict[str, Any]]:
    cached = _case_heads_cache.get(base_url)
    if cached and time.time() - cached[0] < CASE_HEADS_TTL_SECONDS:
        return cached[1]
    payload = response_data(agent_get(base_url, token, "GetCaseHeads"))
    if not isinstance(payload, list) or not payload:
        raise OAError(f"GetCaseHeads 返回异常：{payload!r}")
    heads = [row for row in payload if isinstance(row, dict) and str(row.get("name") or "").strip()]
    _case_heads_cache[base_url] = (time.time(), heads)
    return heads


def _case_head_path(head: dict[str, Any], by_id: dict[int, dict[str, Any]]) -> str:
    names = []
    for part in str(head.get("nodePath") or "").split("."):
        try:
            node = by_id.get(int(part))
        except ValueError:
            continue
        if node:
            names.append(str(node.get("name")))
    return " > ".join(names) if names else str(head.get("name"))


def _match_case_head(
    cause_norm: str, heads: list[dict[str, Any]], base_type: str
) -> dict[str, Any] | None:
    candidates = [h for h in heads if normalize_name(str(h.get("name"))) == cause_norm]
    if not candidates:
        return None
    by_id = {int(h["id"]): h for h in heads if h.get("id") is not None}

    def root_name(head: dict[str, Any]) -> str:
        first = str(head.get("nodePath") or "").split(".")[0]
        try:
            node = by_id.get(int(first))
        except ValueError:
            node = None
        return str(node.get("name")) if node else ""

    def rank(head: dict[str, Any]) -> tuple[int, int]:
        root = root_name(head)
        # 同名节点在多棵树中出现时，优先与案件类型同树、优先叶子节点
        type_match = 0
        if "刑事" in base_type and "刑事" in root:
            type_match = -1
        elif "民事" in base_type and "民事" in root:
            type_match = -1
        return (type_match, 0 if head.get("isLeaf") else 1)

    best = sorted(candidates, key=rank)[0]
    return {
        "id": best.get("id"),
        "name": str(best.get("name")),
        "is_leaf": bool(best.get("isLeaf")),
        "is_root": best.get("parentId") is None,
        "path": _case_head_path(best, by_id),
    }


# 相似度计算时剔除的通用字，避免仅靠「纠纷/罪」等后缀凑出无意义建议
_SUGGESTION_STOP_CHARS = set("纠纷罪案件")


def _cause_suggestions(cause_norm: str, heads: list[dict[str, Any]], limit: int = 5) -> list[str]:
    core = set(cause_norm) - _SUGGESTION_STOP_CHARS
    scored: list[tuple[int, int, str]] = []
    for head in heads:
        name = str(head.get("name"))
        norm = normalize_name(name)
        if not norm:
            continue
        if cause_norm in norm or norm in cause_norm:
            scored.append((0, abs(len(norm) - len(cause_norm)), name))
        elif core:
            common = len((set(norm) - _SUGGESTION_STOP_CHARS) & core)
            if common >= max(2, len(core) // 2):
                scored.append((1, -common, name))
    scored.sort()
    seen: set[str] = set()
    out: list[str] = []
    for _, _, name in scored:
        if name not in seen:
            seen.add(name)
            out.append(name)
        if len(out) >= limit:
            break
    return out


def cause_review(base_url: str, token: str, detail: dict[str, Any]) -> dict[str, Any]:
    """案由规范性审查：案由/罪名必须命中 OA 系统案由字典，自由填写文本阻断。"""
    cause_text = str(detail.get("causeAction") or detail.get("caseHeadName") or "").strip()
    head_name = str(detail.get("caseHeadName") or "").strip()
    if not cause_text:
        # 案由缺失由资料完整性阻断，此处不重复报
        return {"result": "not_applicable", "cause_text": None}

    heads = get_case_heads(base_url, token)
    base_type = str(detail.get("baseTypeName") or detail.get("baseType") or "")

    blockers: list[str] = []
    warnings: list[str] = []
    matches: list[dict[str, Any]] = []
    suggestions: list[str] = []

    # 整串精确匹配优先（罪名本身可含顿号，如「拒不执行判决、裁定罪」），
    # 不命中时再按分隔符拆分逐一匹配（多案由登记场景）
    whole = _match_case_head(normalize_name(cause_text), heads, base_type)
    parts = [cause_text] if whole else split_names(cause_text)
    for part in parts:
        norm = normalize_name(part)
        match = whole if whole else _match_case_head(norm, heads, base_type)
        if match is None:
            suggestions.extend(s for s in _cause_suggestions(norm, heads) if s not in suggestions)
            blockers.append(
                f"案由「{part}」不在 OA 系统案由库中，疑似手工自由填写；"
                "请在 OA 中改选系统案由后重新提交审批"
            )
        elif match["is_root"]:
            blockers.append(
                f"案由「{part}」是案由库的顶级分类节点，不能作为具体案由使用，请选择下级具体案由"
            )
            matches.append(match)
        else:
            if not match["is_leaf"]:
                warnings.append(
                    f"「{match['name']}」在案由库中还有更细分的下级案由，如适用可选更具体的（不影响通过）"
                )
            matches.append(match)

    if not blockers and head_name and normalize_name(head_name) != normalize_name(cause_text):
        warnings.append(f"登记案由「{cause_text}」与字典关联案由「{head_name}」不一致，请核实以哪个为准")

    return {
        "result": "blocked" if blockers else "ok",
        "cause_text": cause_text,
        "matches": matches,
        "blockers": blockers,
        "warnings": warnings,
        "suggestions": suggestions,
    }


# ------------------------------------------------------- approval reviews

# 非诉讼业务类型：不按诉讼立案标准审查。这类业务没有诉讼阶段，收费灵活（含免费
# 咨询），故不强制「案件阶段」、不作 5000 元低收费门槛审查。baseTypeName 是 OA
# 案件基础大类，2026-07-10 全所 3468 件实证分布确认（咨询代书/顾问签约/非诉/公益）。
NON_LITIGATION_BASE_TYPES = {"咨询代书", "顾问签约", "非诉业务", "公益法律"}


def is_non_litigation(detail: dict[str, Any]) -> bool:
    return (detail.get("baseTypeName") or "") in NON_LITIGATION_BASE_TYPES


def is_criminal_case(detail: dict[str, Any]) -> bool:
    classifications = (
        detail.get("baseTypeName"),
        detail.get("baseType"),
        detail.get("caseCategoryName"),
    )
    if any("刑事" in str(value or "") for value in classifications):
        return True

    # OA 允许刑事法律援助案件登记在「公益法律」等业务大类下，此时规范
    # 罪名才是案件性质的可靠信号。
    cause = str(detail.get("causeAction") or detail.get("caseHeadName") or "").strip()
    return cause.endswith("罪")


def completeness_review(
    detail: dict[str, Any],
    entity: dict[str, Any],
    *,
    non_litigation: bool = False,
    criminal_case: bool = False,
) -> dict[str, Any]:
    principals, opponents = party_names(detail)
    # 案情摘要缺失不拦截（2026-07-08 合伙人确认），只作提示
    checks = {
        "委托人": principals,
        "对方": opponents,
        "经办律师": detail.get("empNames") or detail.get("employees"),
        "案由": detail.get("causeAction") or detail.get("caseHeadName"),
        "案件阶段": detail.get("instances"),
        "收费方式": detail.get("chargeMethodName") or entity.get("chargeMethd"),
        "委托收费金额": detail.get("chargeAmount"),
    }
    if non_litigation:
        # 非诉讼业务无诉讼阶段，不要求「案件阶段」
        checks.pop("案件阶段", None)
    if criminal_case:
        # 刑事案件无民事/行政相对方，不要求「对方」
        checks.pop("对方", None)
    missing = [label for label, value in checks.items() if value in (None, "", [])]
    warnings = []
    if detail.get("caseSummary") in (None, ""):
        warnings.append("案情摘要未填写（不影响通过）")
    if non_litigation:
        warnings.append("本案为非诉讼业务，已放宽审查：不要求案件阶段、不作低收费门槛审查")
    if criminal_case:
        warnings.append("本案为刑事案件，已放宽审查：不要求对方当事人")
    return {
        "result": "blocked" if missing else "complete",
        "missing": missing,
        "warnings": warnings,
        "non_litigation": non_litigation,
        "criminal_case": criminal_case,
    }


def fee_explanation_review(
    detail: dict[str, Any], entity: dict[str, Any], *, non_litigation: bool = False
) -> dict[str, Any]:
    """低收费审查：委托收费低于 5000 元必须有收费说明（ChargeMemo），否则不能通过。

    非诉讼业务（咨询代书/顾问签约等）收费灵活、可能免费，不适用此门槛。
    """
    amount = decimal_value(detail.get("chargeAmount"))
    memo = str(entity.get("ChargeMemo") or "").strip()
    if non_litigation:
        return {
            "result": "not_applicable",
            "amount": float(amount) if amount is not None else None,
            "memo": memo or None,
            "non_litigation": True,
            "note": "非诉讼业务不适用低收费门槛审查",
        }
    if amount is None or amount >= Decimal("5000"):
        return {"result": "not_applicable", "amount": float(amount) if amount is not None else None, "memo": memo or None}
    if not memo:
        return {
            "result": "blocked",
            "amount": float(amount),
            "memo": None,
            "blockers": [f"委托收费 {amount} 元低于 5000 元且未填写收费说明，不能通过；请在 OA 补充收费说明后重新检查"],
        }
    memo_amounts = extract_fee_amounts(memo)
    if not fee_amounts_match(amount, memo_amounts):
        return {
            "result": "blocked",
            "amount": float(amount),
            "memo": memo,
            "memo_amounts": [float(a) for a in memo_amounts],
            "blockers": [
                f"收费说明记载金额（{format_amounts(memo_amounts)}）与 OA 登记委托收费 {amount:,.0f} 元不一致，"
                "登记与说明存在冲突；请核实以书面合同为准更正后重新检查"
            ],
        }
    return {"result": "ok", "amount": float(amount), "memo": memo, "blockers": []}


def conflict_review(base_url: str, token: str, detail: dict[str, Any], lawcase_id: int) -> dict[str, Any]:
    principals, opponents = party_names(detail)
    principal_keys = {normalize_name(name) for name in principals}
    opponent_keys = {normalize_name(name) for name in opponents}
    blockers = []
    findings = []
    if principal_keys & opponent_keys:
        blockers.append("本案委托人与对方存在同名主体，必须更正或核实主体身份")

    searched: dict[str, list[dict[str, Any]]] = {}
    for name in dict.fromkeys(principals + opponents):
        searched[name] = get_case_list_all(base_url, token, name)

    seen = set()
    for searched_name, rows in searched.items():
        key = normalize_name(searched_name)
        for row in rows:
            row_id = row_case_id(row)
            if row_id == lawcase_id:
                continue
            row_principals = {normalize_name(x) for x in split_names(row.get("wtrNames") or row.get("dsrNames"))}
            row_opponents = {normalize_name(x) for x in split_names(row.get("tosNames"))}
            relation = None
            if key in principal_keys and key in row_opponents:
                relation = "本案委托人曾/正在作为本所案件对方"
            elif key in opponent_keys and key in row_principals:
                relation = "本案对方曾/正在作为本所委托人"
            if not relation:
                continue
            identity = (row_id, relation, key)
            if identity in seen:
                continue
            seen.add(identity)
            status = int(row.get("status") or 0)
            findings.append(
                {
                    "matched_name": searched_name,
                    "relation": relation,
                    "severity": "high" if status in ACTIVE_CASE_STATUSES else "review",
                    "case_id": row_id,
                    "case_no": row.get("no") or row.get("preNo"),
                    "status": status,
                    "status_name": row.get("statusName"),
                    "wtr_names": row.get("wtrNames"),
                    "tos_names": row.get("tosNames"),
                    "cause": row.get("causeAction"),
                }
            )

    return {
        "result": "blocked" if blockers else ("manual_review_required" if findings else "no_exact_adverse_match"),
        "principals": principals,
        "opponents": opponents,
        "blockers": blockers,
        "findings": findings,
        "limitations": [
            "仅检索OA中可见案件并按规范化后的主体名称精确比对",
            "同名、曾用名、关联企业、实际控制人和未录入OA事项仍须人工核验",
            "命中是风险线索，不等于已经构成法律上的利益冲突",
        ],
    }


def duplicate_filing_review(base_url: str, token: str, detail: dict[str, Any], lawcase_id: int) -> dict[str, Any]:
    principals, opponents = party_names(detail)
    principal_keys = {normalize_name(name): name for name in principals}
    opponent_keys = {normalize_name(name): name for name in opponents}
    current_cause = normalize_name(str(detail.get("causeAction") or detail.get("caseHeadName") or ""))

    searched: dict[str, list[dict[str, Any]]] = {}
    for name in dict.fromkeys(principals + opponents):
        searched[name] = get_case_list_all(base_url, token, name)

    candidates: dict[int, dict[str, Any]] = {}
    for rows in searched.values():
        for row in rows:
            row_id = row_case_id(row)
            if not row_id or row_id == lawcase_id:
                continue
            candidates.setdefault(row_id, row)

    blockers: list[str] = []
    findings: list[dict[str, Any]] = []
    for row_id, row in candidates.items():
        row_principals = {normalize_name(x): x for x in split_names(row.get("wtrNames") or row.get("dsrNames"))}
        row_opponents = {normalize_name(x): x for x in split_names(row.get("tosNames"))}
        row_cause = normalize_name(str(row.get("causeAction") or row.get("caseHeadName") or ""))
        principal_overlap = [principal_keys[k] for k in principal_keys.keys() & row_principals.keys()]
        opponent_overlap = [opponent_keys[k] for k in opponent_keys.keys() & row_opponents.keys()]
        any_party_overlap = bool(
            (set(principal_keys) | set(opponent_keys)) & (set(row_principals) | set(row_opponents))
        )
        cause_match = bool(current_cause and row_cause and current_cause == row_cause)
        status = row_status(row)

        exact_triple = bool(principal_overlap and opponent_overlap and cause_match)
        if exact_triple and status in ACTIVE_DUPLICATE_STATUSES:
            severity = "block"
            relation = "同委托人+同对方+同案由的OA在办/待处理案件"
            blockers.append(f"OA内疑似重复立案: {row.get('no') or row.get('preNo') or row_id} {relation}")
        elif exact_triple and status == 2:
            severity = "review"
            relation = "同委托人+同对方+同案由的历史「立案未通过」记录，可能为驳回后重新申报，请核对前次驳回问题是否已补正"
        elif exact_triple:
            severity = "review"
            relation = "同委托人+同对方+同案由的历史案件（已结案/已撤销/已归档），请判断是否为新阶段立案"
        elif (cause_match and any_party_overlap) or (principal_overlap and opponent_overlap):
            severity = "review"
            relation = "部分当事人/案由重叠，需合伙人判断是否关联或重复"
        else:
            continue

        findings.append(
            {
                "severity": severity,
                "relation": relation,
                "case_id": row_id,
                "case_no": row.get("no") or row.get("preNo"),
                "status": status,
                "status_name": row.get("statusName"),
                "wtr_names": row.get("wtrNames"),
                "tos_names": row.get("tosNames"),
                "cause": row.get("causeAction") or row.get("caseHeadName"),
                "emp_names": row.get("empNames"),
                "principal_overlap": principal_overlap,
                "opponent_overlap": opponent_overlap,
                "cause_match": cause_match,
            }
        )

    return {
        "result": "blocked" if blockers else ("manual_review_required" if findings else "no_duplicate_filing_match"),
        "principals": principals,
        "opponents": opponents,
        "cause": detail.get("causeAction") or detail.get("caseHeadName"),
        "blockers": blockers,
        "findings": findings,
        "limitations": [
            "按OA可见案件做名称与案由精确匹配",
            "同名不同主体、案由登记不一致、未录入OA案件仍须人工复核",
        ],
    }


def is_risk_charge(detail: dict[str, Any], entity: dict[str, Any]) -> bool:
    method_name = str(detail.get("chargeMethodName") or "")
    method = entity.get("chargeMethd")
    method_id = method.get("Id") if isinstance(method, dict) else method
    return "风险" in method_name or str(method_id or "") == str(RISK_CHARGE_METHOD_ID)


def risk_cap_breakdown(subject_amount: Decimal) -> list[dict[str, Any]]:
    """Per-tier calculation lines for the graduated cap, for display."""
    lines = []
    remaining = subject_amount
    lower = Decimal("0")
    for width, rate in RISK_FEE_TIERS:
        if remaining <= 0:
            break
        portion = remaining if width is None else min(remaining, width)
        upper = None if width is None else lower + width
        lines.append(
            {
                "range": f"{lower:,.0f} 元以上" if upper is None else f"{lower:,.0f} — {upper:,.0f} 元",
                "rate": f"{rate * 100:.0f}%",
                "portion": float(portion),
                "fee": float((portion * rate).quantize(Decimal("0.01"))),
            }
        )
        remaining -= portion
        lower = upper if upper is not None else lower
    return lines


def risk_charge_review(detail: dict[str, Any], entity: dict[str, Any], risk_fee_amount: Any = None) -> dict[str, Any]:
    """风险代理审查只核验 OA 中可机器读取的风险条款与收费数据。

    规则完整、未命中禁止范围且金额未超限时可以自动通过；任何资料外
    判断（例如合同是否实际签署）都不会由自动审批代替人工判断。
    """
    if not is_risk_charge(detail, entity):
        return {"result": "not_applicable", "charge_method": detail.get("chargeMethodName")}

    description = " ".join(
        str(value or "")
        for value in (
            detail.get("baseTypeName"),
            detail.get("caseCategoryName"),
            detail.get("causeAction"),
            detail.get("caseHeadName"),
            detail.get("caseSummary"),
        )
    )
    prohibited_hits = [kw for kw in RISK_PROHIBITED_KEYWORDS if kw in description]
    base_type = str(detail.get("baseTypeName") or detail.get("baseType") or "")
    if "行政" in base_type and "行政诉讼" not in prohibited_hits:
        prohibited_hits.append("行政诉讼")

    scheme = str(entity.get("ChargeMemo") or "").strip() or None
    subject_amount = decimal_value(entity.get("Biaodi") or detail.get("biaodi"))
    registered_fee = decimal_value(detail.get("chargeAmount"))
    cap = risk_fee_cap(subject_amount)

    issues: list[str] = []
    suggestions: list[str] = []
    if prohibited_hits:
        issues.append("案件描述命中风险代理禁止适用情形: " + "、".join(prohibited_hits))
        suggestions.append("若确属禁止范围，应驳回并改用计件/计时等收费方式")
    if not scheme:
        issues.append("OA 未填写收费方案（收费说明），无法审查具体收费结构")
        suggestions.append("要求经办律师在 OA 补充完整收费方案后重新审查")
    if subject_amount is None:
        issues.append("缺少标的额，无法计算风险代理分段收费上限")
        suggestions.append("补充标的额，或按合同争议金额人工核算上限")
    if cap is not None and registered_fee is not None and registered_fee > cap:
        issues.append(f"OA 登记收费 {registered_fee:,.0f} 元已超过分段上限 {cap:,.0f} 元")
        suggestions.append("核对收费方案约定的最高可能收费，超上限应要求调整")

    scheme_amounts = extract_fee_amounts(scheme) if scheme else []
    if scheme_amounts and registered_fee is not None and not fee_amounts_match(registered_fee, scheme_amounts):
        issues.append(
            f"收费方案记载金额（{format_amounts(scheme_amounts)}）与 OA 登记收费 {registered_fee:,.0f} 元不一致，"
            "登记与方案存在冲突"
        )
        suggestions.append("核对书面合同实际约定，更正 OA 登记收费或收费方案后再审批")
    if cap is not None and scheme_amounts and sum(scheme_amounts) > cap:
        issues.append(
            f"收费方案记载固定金额合计 {sum(scheme_amounts):,.0f} 元已超过分段上限 {cap:,.0f} 元（尚未计入比例收费部分）"
        )
        suggestions.append("按方案各环节费用最高可能合计核算，超上限应要求调整方案")

    if not issues:
        verdict = "pass"
        if cap is not None:
            suggestions.append(
                f"OA 已登记的风险条款符合当前可核验规则，收费上限为 {cap:,.0f} 元"
            )
    else:
        verdict = "issues_found"

    return {
        "result": "auto_pass" if not issues else "manual_confirmation_required",
        "verdict": verdict,
        "charge_method": detail.get("chargeMethodName"),
        "scheme": scheme,
        "subject_amount": float(subject_amount) if subject_amount is not None else None,
        "registered_fee": float(registered_fee) if registered_fee is not None else None,
        "scheme_amounts": [float(a) for a in scheme_amounts],
        "graduated_cap": float(cap) if cap is not None else None,
        "cap_breakdown": risk_cap_breakdown(subject_amount) if subject_amount is not None else [],
        "prohibited_matches": prohibited_hits,
        "issues": issues,
        "suggestions": suggestions,
        "notes": [
            "系统只使用 OA 已登记的收费方案与金额；缺失、矛盾或无法核验时一律转人工",
            "是否签署专门书面合同等材料事实不在自动审批范围内",
        ],
        "basis": "司发通〔2021〕87号第四至七项",
    }


def build_approval_review(
    base_url: str,
    token: str,
    lawcase_id: int,
    detail: dict[str, Any],
    risk_fee_amount: float | None = None,
) -> dict[str, Any]:
    entity = get_case_entity(base_url, token, lawcase_id, detail)
    non_lit = is_non_litigation(detail)
    criminal = is_criminal_case(detail)
    return {
        "lawcase_id": lawcase_id,
        "case_no": detail.get("no") or detail.get("preNo"),
        "status": detail.get("status"),
        "status_name": detail.get("statusName"),
        "base_type_name": detail.get("baseTypeName"),
        "non_litigation": non_lit,
        "completeness": completeness_review(detail, entity, non_litigation=non_lit, criminal_case=criminal),
        "cause": cause_review(base_url, token, detail),
        "conflict": conflict_review(base_url, token, detail, lawcase_id),
        "duplicate_filing": duplicate_filing_review(base_url, token, detail, lawcase_id),
        "fee_explanation": fee_explanation_review(detail, entity, non_litigation=non_lit),
        "risk_charge": risk_charge_review(detail, entity, risk_fee_amount),
    }


def approval_gate_errors(
    review: dict[str, Any],
    *,
    conflict_reviewed: bool = False,
    conflict_memo: str = "",
    risk_reviewed: bool = False,
) -> list[str]:
    errors = [f"资料不完整: {v}" for v in (review["completeness"].get("missing") or [])]
    errors.extend(review.get("cause", {}).get("blockers") or [])
    errors.extend(review["conflict"].get("blockers") or [])
    findings = review["conflict"].get("findings") or []
    if findings and not (conflict_reviewed and conflict_memo.strip()):
        errors.append("存在利冲检索命中，须确认合伙人已人工复核并填写复核结论")
    errors.extend(review.get("duplicate_filing", {}).get("blockers") or [])
    errors.extend(review.get("fee_explanation", {}).get("blockers") or [])
    risk = review["risk_charge"]
    if risk.get("result") == "manual_confirmation_required" and not risk_reviewed:
        errors.append("风险代理收费须合伙人审阅收费方案与初步判断后勾选确认")
    return errors


# ------------------------------------------------------- approval actions


def post_lian_approval(base_url: str, token: str, lawcase_id: int, approved: bool, memo: str) -> Any:
    result = post_form(
        base_url,
        token,
        "/DataServices/LawcaseSvr/Lianshenpi",
        {
            "lId": str(lawcase_id),
            "isApproved": "true" if approved else "false",
            "memo": memo,
        },
    )
    if isinstance(result, dict) and (result.get("Type") or result.get("Message")):
        raise OAError(result.get("Message") or json.dumps(result, ensure_ascii=False))
    return result


def post_lian_fanshen(base_url: str, token: str, lawcase_id: int) -> Any:
    """反审批：将已通过(3)或已驳回(2)的立案申请退回立案待审(1)。

    OA 端点为 JSON body（区别于 Lianshenpi 的表单编码），成功返回字符串 "1"。
    """
    url = urljoin(base_url.rstrip("/") + "/", "DataServices/LawcaseSvr/LianFanshen")
    resp = _http.post(
        url,
        headers={"nedev_access_token": token},
        json={"lawcaseIds": str(lawcase_id)},
        timeout=30,
    )
    resp.raise_for_status()
    try:
        result = resp.json()
    except ValueError:
        result = resp.text
    if isinstance(result, str) and result.strip() == "1":
        return result
    if isinstance(result, dict) and (result.get("Type") or result.get("Message")):
        raise OAError(result.get("Message") or json.dumps(result, ensure_ascii=False))
    raise OAError(f"反审失败：{result!r}")


def verify_status_change(base_url: str, token: str, lawcase_id: int, expected_status: int) -> dict[str, Any]:
    after: dict[str, Any] = {}
    for _ in range(5):
        after = get_case_detail(base_url, token, lawcase_id)
        if row_status(after) == expected_status:
            return after
        time.sleep(1)
    raise OAError(
        f"审批请求已提交但回读校验失败：期望 status={expected_status}，实际 {after.get('status')}（{after.get('statusName')}）"
    )


# ------------------------------------------------------------- documents
# 链路（skill 侧 2026-06-17 案件 3898 实测验证）：
# GetWordTemplates → ExportWordTemplates → 带 token GET downloadUrl

DOC_DOWNLOAD_TIMEOUT = 120

_ORG_NAME_RE = re.compile(r"(分公司|办事处|合伙企业|合伙)$")
_LEGAL_PERSON_NAME_RE = re.compile(r"(公司|集团|银行|医院|学校|合作社|事务所|研究院|保险)$")


def get_word_templates(base_url: str, token: str, lawcase_id: int) -> list[dict[str, Any]]:
    payload = response_data(agent_get(base_url, token, "GetWordTemplates", {"lawcaseId": lawcase_id}))
    if not isinstance(payload, list):
        raise OAError(f"GetWordTemplates 返回异常：{payload!r}")
    return [row for row in payload if isinstance(row, dict)]


def export_word_template(
    base_url: str, token: str, lawcase_id: int, template_name: str
) -> tuple[bytes, str | None]:
    """导出单个文书模板并下载，返回 (文件字节, OA 提供的文件名或 None)。"""
    payload = response_data(
        agent_get(
            base_url,
            token,
            "ExportWordTemplates",
            {"lawcaseId": lawcase_id, "fileTemplateNames": template_name},
        )
    )
    download_url = payload.get("downloadUrl") if isinstance(payload, dict) else None
    if not download_url:
        raise OAError(f"ExportWordTemplates 未返回下载地址：{payload!r}")
    url = str(download_url)
    if not url.lower().startswith("http"):
        url = urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
    resp = _http.get(url, headers={"nedev_access_token": token}, timeout=DOC_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    filename = None
    disposition = resp.headers.get("Content-Disposition") or ""
    match = re.search(r"filename\*=UTF-8''([^;]+)", disposition, re.IGNORECASE)
    if match:
        filename = unquote(match.group(1))
    else:
        match = re.search(r'filename="?([^";]+)"?', disposition)
        if match:
            filename = match.group(1)
    return resp.content, filename


def principal_org_kinds(detail: dict[str, Any]) -> tuple[list[str], list[str]]:
    """识别委托人中的法人与非法人组织，优先看 identityTypeName，缺失时按名称兜底。"""
    legal_persons: list[str] = []
    orgs: list[str] = []
    for row in detail.get("clients") or []:
        if not isinstance(row, dict) or row.get("roleType") != 0:
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        identity = str(row.get("identityTypeName") or "")
        if "非法人" in identity or "其他组织" in identity:
            orgs.append(name)
        elif "法人" in identity:
            legal_persons.append(name)
        elif _ORG_NAME_RE.search(name):
            orgs.append(name)
        elif _LEGAL_PERSON_NAME_RE.search(name):
            legal_persons.append(name)
    return legal_persons, orgs


def companion_documents(
    detail: dict[str, Any], available: list[str], selected: list[str]
) -> tuple[list[str], list[str]]:
    """委托类文书的必带证明书（2026-06-17 硬规则）：

    委托人为法人 → 必须附带法定代表（人）身份证明书；
    委托人为非法人组织 → 附带负责人证明书。
    返回 (需自动追加的模板名, 说明文字)。
    """
    if not any("委托" in name for name in selected):
        return [], []
    legal_persons, orgs = principal_org_kinds(detail)
    additions: list[str] = []
    notes: list[str] = []

    def find_template(*keywords: str) -> str | None:
        for name in available:
            if any(kw in name for kw in keywords):
                return name
        return None

    if legal_persons:
        target = find_template("法定代表身份证明", "法定代表人身份证明", "法人代表证明")
        if target and target not in selected:
            additions.append(target)
            notes.append(f"委托人 {'、'.join(legal_persons)} 为法人，已自动附带《{target}》")
        elif not target:
            notes.append(
                f"委托人 {'、'.join(legal_persons)} 为法人，但本案模板列表中未找到法定代表人身份证明文书，请人工核对补充"
            )
    if orgs:
        target = find_template("负责人证明")
        if target and target not in selected and target not in additions:
            additions.append(target)
            notes.append(f"委托人 {'、'.join(orgs)} 为非法人组织，已自动附带《{target}》")
        elif not target:
            notes.append(
                f"委托人 {'、'.join(orgs)} 为非法人组织，但本案模板列表中未找到负责人证明书，请人工核对补充"
            )
    return additions, notes
