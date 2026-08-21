#!/usr/bin/env python3
"""只读探针：登录 OA，拉取指定案件的 GetEntity 返回，打印全部字段名。

用法：
  cd backend && .venv/bin/python probe_entity_fields.py <案件ID> [案件ID ...]

环境变量（二选一）：
  OA_USERNAME + OA_PASSWORD   账号密码登录（推荐）
  OA_API_KEY                  AgentAPI Key 登录

本脚本只读，不写入 OA，不改变任何案件状态。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app import oa

BASE_URL = oa.DEFAULT_BASE_URL


def main() -> None:
    if len(sys.argv) < 2:
        print("用法：probe_entity_fields.py <案件ID> [案件ID ...]")
        sys.exit(1)

    ids = [int(arg) for arg in sys.argv[1:]]

    username = os.environ.get("OA_USERNAME")
    password = os.environ.get("OA_PASSWORD")
    api_key = os.environ.get("OA_API_KEY")

    if username and password:
        token, info = oa.login_with_password(BASE_URL, username, password)
        print(f"登录成功：{info.get('UserName') or info.get('userName') or username}")
    elif api_key:
        token = oa.login(BASE_URL, api_key)
        print("登录成功（API Key）")
    else:
        print("请设置 OA_USERNAME + OA_PASSWORD 或 OA_API_KEY 环境变量")
        sys.exit(1)

    for lawcase_id in ids:
        print(f"\n{'='*60}")
        print(f"案件 ID: {lawcase_id}")
        print(f"{'='*60}")
        try:
            detail = oa.get_case_detail(BASE_URL, token, lawcase_id)
        except Exception as exc:
            print(f"  get_case_detail 失败：{exc}")
            continue

        print(f"\n--- detail (GetLawcaseDetail) 字段名 ---")
        for key in sorted(detail.keys()):
            value = detail.get(key)
            preview = json.dumps(value, ensure_ascii=False, default=str)
            if len(preview) > 120:
                preview = preview[:117] + "..."
            print(f"  {key}: {preview}")

        try:
            entity = oa.get_case_entity(BASE_URL, token, lawcase_id, detail)
        except Exception as exc:
            print(f"\n  get_case_entity 失败：{exc}")
            continue

        print(f"\n--- entity (GetEntity) 字段名 ---")
        if not entity:
            print("  (空)")
        else:
            for key in sorted(entity.keys()):
                value = entity.get(key)
                preview = json.dumps(value, ensure_ascii=False, default=str)
                if len(preview) > 120:
                    preview = preview[:117] + "..."
                print(f"  {key}: {preview}")

        base_type = str(detail.get("baseTypeName") or "")
        print(f"\n--- 案件类型识别 ---")
        print(f"  baseTypeName: {base_type}")
        print(f"  normalized_case_type: {oa.normalized_case_type(detail)}")
        merged = {**detail, **entity}
        date_like = {k: v for k, v in merged.items()
                     if any(w in k.lower() for w in ("date", "start", "end", "begin", "finish", "guwen", "service"))}
        if date_like:
            print(f"\n--- 日期/起止相关字段（detail + entity 合并）---")
            for k, v in sorted(date_like.items()):
                print(f"  {k}: {v}")

    print("\n完成。以上为只读结果，未写入 OA。")


if __name__ == "__main__":
    main()
