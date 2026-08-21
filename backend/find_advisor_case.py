#!/usr/bin/env python3
"""只读发现：从待审列表里找出法律顾问类案件，返回 ID 和基本信息。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app import oa

BASE_URL = oa.DEFAULT_BASE_URL


def main() -> None:
    username = os.environ.get("OA_USERNAME")
    password = os.environ.get("OA_PASSWORD")
    if not username or not password:
        print("请设置 OA_USERNAME + OA_PASSWORD 环境变量")
        sys.exit(1)

    token, info = oa.login_with_password(BASE_URL, username, password)
    print(f"登录成功：{info.get('UserName') or info.get('userName') or username}")

    keywords = sys.argv[1:] if len(sys.argv) > 1 else ["顾问"]
    print(f"搜索关键词：{keywords}")

    seen: dict[int, dict] = {}
    for status in (1, 3, 4, 5, 2, -2, -1):
        page = 0
        while True:
            payload = oa.get_case_list(BASE_URL, token, {"status": status, "pageIndex": page, "pageSize": 100})
            batch = payload.get("data") or []
            for r in batch:
                cid = oa.row_case_id(r)
                if cid:
                    seen[cid] = r
            total = int(payload.get("total") or 0)
            if len(batch) < 100 or (total and len(seen) >= total):
                break
            page += 1

    rows = list(seen.values())

    print(f"\n共 {len(rows)} 条立案待审。筛顾问类：")
    advisor_keywords = ("顾问", "guwen")
    advisor_keywords = ("顾问", "guwen")
    advisor_rows = [
        r for r in rows
        if any(k in str(r.get("baseTypeName") or "") for k in advisor_keywords)
        or any(k in str(r.get("causeAction") or "") for k in keywords)
    ]

    target_rows = []
    if any(k in keywords for k in advisor_keywords) or "顾问" in keywords:
        target_rows = [
            r for r in rows
            if any(k in str(r.get("baseTypeName") or "") for k in advisor_keywords)
            or any(k in str(r.get("causeAction") or "") for k in keywords)
        ]
    else:
        target_rows = [
            r for r in rows
            if any(k in str(r.get("baseTypeName") or "") for k in keywords)
            or any(k in str(r.get("causeAction") or "") for k in keywords)
        ]

    for r in target_rows:
        case_id = oa.row_case_id(r)
        print(f"\n  ID={case_id} 案号={r.get('no') or r.get('preNo')}")
        print(f"    类型={r.get('baseTypeName')!r}")
        print(f"    委托人={r.get('wtrNames')}")
        print(f"    对方={r.get('tosNames')}")
        print(f"    案由={r.get('causeAction')}")
        print(f"    收费金额={r.get('chargeAmount')}")
        print(f"    受理日期={r.get('shouliDate')}")
        print(f"    提交时间={r.get('submitTime') or r.get('createTime')}")

    if not advisor_rows:
        print("  (未找到顾问类案件)")
        print("\n非顾问类的案件类型分布：")
        from collections import Counter
        c = Counter(str(r.get("baseTypeName") or "") for r in rows)
        for k, v in c.most_common():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
