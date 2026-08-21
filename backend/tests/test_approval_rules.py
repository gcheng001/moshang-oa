from __future__ import annotations

import unittest
from unittest.mock import patch

from app import oa


class ApprovalRuleTests(unittest.TestCase):
    def test_all_eleven_case_types_are_recognized(self) -> None:
        raw = [
            "民事案件", "刑事案件", "行政案件", "执行案件", "法律顾问签约",
            "非诉业务", "仲裁业务", "咨询代书", "赔偿案件", "破产诉讼案件", "公益法律",
        ]
        self.assertEqual(
            [oa.normalized_case_type({"baseTypeName": value}) for value in raw],
            list(oa.CANONICAL_CASE_TYPES),
        )

    def test_litigation_fee_below_5000_requires_specific_reason(self) -> None:
        vague = oa.fee_explanation_review(
            {"chargeAmount": 3000}, {"ChargeMemo": "领导同意"}, non_litigation=False
        )
        specific = oa.fee_explanation_review(
            {"chargeAmount": 3000}, {"ChargeMemo": "当事人经济困难，协议收费3000元"}, non_litigation=False
        )
        self.assertEqual(vague["result"], "blocked")
        self.assertEqual(specific["result"], "ok")

    def test_zero_fee_accepts_prior_firm_charge_explanation(self) -> None:
        result = oa.fee_explanation_review(
            {"chargeAmount": 0},
            {"ChargeMemo": "在前所收费5000元，所以在本案不再收费"},
            non_litigation=False,
        )

        self.assertEqual(result["result"], "ok")
        self.assertEqual(result["amount"], 0.0)
        self.assertEqual(result["memo_amounts"], [5000.0])
        self.assertTrue(result["prior_charge_explanation"])

    def test_zero_fee_does_not_accept_current_case_charge_as_prior_charge(self) -> None:
        result = oa.fee_explanation_review(
            {"chargeAmount": 0},
            {"ChargeMemo": "一审案件，本案收费5000元，支付后本案不再另行收费"},
            non_litigation=False,
        )

        self.assertEqual(result["result"], "blocked")

    def test_non_litigation_is_exempt_from_5000_gate(self) -> None:
        result = oa.fee_explanation_review(
            {"chargeAmount": 0}, {}, non_litigation=True
        )
        self.assertEqual(result["result"], "not_applicable")

    @patch("app.oa.get_case_heads")
    def test_public_interest_case_does_not_require_category_or_cause(self, get_heads) -> None:
        """公益法律只验证 OA 系统大类，不要求子分类或案由字典匹配。"""
        detail = {
            "baseTypeId": 11,
            "baseTypeName": "公益法律",
            "caseCategoryId": None,
            "caseHeadId": None,
            "caseHeadName": None,
            "causeAction": "",
            "chargeMethodId": 7,
            "chargeMethodName": "免费",
            "chargeAmount": 0,
            "empNames": "测试律师",
            "clients": [{"roleType": 0, "name": "测试服务对象"}],
        }
        entity = {"baseType": 11, "caseCategory": None, "caseHead": None, "chargeMethd": 7}

        completeness = oa.completeness_review(detail, entity, non_litigation=True)
        options = oa.system_option_review("https://example.invalid", "token", detail, entity)
        cause = oa.cause_review("https://example.invalid", "token", detail)

        self.assertEqual(completeness["result"], "complete")
        self.assertNotIn("公益事项", completeness["missing"])
        self.assertEqual(options["result"], "ok")
        self.assertEqual(cause["result"], "not_applicable")
        self.assertFalse(cause["blockers"])
        get_heads.assert_not_called()

    def test_public_interest_case_still_requires_system_base_type(self) -> None:
        result = oa.system_option_review(
            "https://example.invalid",
            "token",
            {"baseTypeName": "公益法律", "baseTypeId": None},
            {"baseType": None},
        )
        self.assertEqual(result["result"], "blocked")
        self.assertTrue(any("公益法律大类" in reason for reason in result["blockers"]))

    def test_missing_entity_is_technical_not_business_rejection(self) -> None:
        result = oa.system_option_review("https://example.invalid", "token", {"baseTypeName": "民事案件"}, {})
        self.assertEqual(result["result"], "technical_error")
        self.assertFalse(result["blockers"])

    @patch("app.oa.get_case_heads", return_value=[{"id": 1, "name": "合同纠纷", "isLeaf": True, "parentId": 2}])
    def test_free_text_cause_not_in_system_dictionary_is_blocked(self, _heads) -> None:
        result = oa.system_option_review(
            "https://example.invalid",
            "token",
            {
                "baseTypeName": "民事案件",
                "causeAction": "自己添加的案由",
                "instances": [{"id": 1, "roles": [{"id": 2}]}],
            },
            {"caseCategory": {"Id": 5}, "chargeMethd": {"Id": 1}},
        )
        self.assertEqual(result["result"], "blocked")
        self.assertTrue(any("不是 OA 系统选项" in reason for reason in result["blockers"]))

    def test_risk_fee_pre_approval_without_contract_is_not_blocked(self) -> None:
        """先审批后签约：审批阶段没有合同/告知登记不应产生不符合项。"""
        result = oa.risk_charge_review(
            {
                "baseTypeName": "民事案件", "causeAction": "合同纠纷",
                "chargeMethodName": "风险代理", "chargeAmount": 10000,
            },
            {"chargeMethd": {"Id": 5}, "ChargeMemo": "收费10000元", "Biaodi": 100000},
        )
        contract_related = [
            i for i in result["issues"] if "合同" in i or "协议" in i or "告知" in i or "提示" in i
        ]
        self.assertFalse(contract_related, f"不应要求审批阶段已登记合同/告知，实际 issues={result['issues']}")

    def test_risk_fee_percent_clause_over_cap_is_flagged(self) -> None:
        """截图案例：标的 65,000，先收 1 万 + 回款 30%，估算 29,500 超 11,700 上限。"""
        result = oa.risk_charge_review(
            {
                "baseTypeName": "民事案件", "causeAction": "合同纠纷",
                "chargeMethodName": "风险代理", "chargeAmount": 10000,
            },
            {
                "chargeMethd": {"Id": 5},
                "ChargeMemo": "按照半风险收费，先收取1万元，后按照回款金额的30%（包括但不限于和解、调解、执行等方式收回款项）",
                "Biaodi": 65000,
            },
        )
        over_cap = [i for i in result["issues"] if "已超过分段收费上限" in i]
        self.assertTrue(over_cap, f"应报告比例条款超上限，实际 issues={result['issues']}")
        self.assertIn("30%", over_cap[0])
        self.assertIn("29,500", over_cap[0])
        self.assertEqual(result["result"], "blocked")

    def test_risk_fee_percent_clause_within_cap_not_flagged(self) -> None:
        """比例条款未超上限时不应误报比例问题。"""
        result = oa.risk_charge_review(
            {
                "baseTypeName": "民事案件", "causeAction": "合同纠纷",
                "chargeMethodName": "风险代理", "chargeAmount": 10000,
            },
            {
                "chargeMethd": {"Id": 5},
                "ChargeMemo": "风险代理，先收取1万元，后按照回款金额的5%收取",
                "Biaodi": 100000,
            },
        )
        over_cap = [i for i in result["issues"] if "已超过分段收费上限" in i]
        self.assertFalse(over_cap, f"未超上限不应误报，实际 issues={result['issues']}")
        self.assertEqual(result["result"], "auto_pass")

    def test_risk_fee_verdict_is_preliminary_pass_not_pass(self) -> None:
        """风险代理初步符合规定时 verdict 取值应为 'preliminary_pass'，与前端契约一致。"""
        result = oa.risk_charge_review(
            {
                "baseTypeName": "民事案件", "causeAction": "合同纠纷",
                "chargeMethodName": "风险代理", "chargeAmount": 10000,
            },
            {"chargeMethd": {"Id": 5}, "ChargeMemo": "风险代理，固定收费1万元", "Biaodi": 100000},
        )
        self.assertEqual(result["verdict"], "preliminary_pass")
        self.assertEqual(result["result"], "auto_pass")

    def test_hard_errors_include_only_confirmed_violations(self) -> None:
        """approval_hard_errors 只取确定性违规，conflict/duplicate 的 findings 都不入。"""
        review = {
            "completeness": {"missing": ["经办律师"]},
            "system_options": {"blockers": ["案件分类不是 OA 系统选项"]},
            "cause": {"blockers": ["案由不在 OA 字典"]},
            "conflict": {
                "blockers": ["委托人与对方同名"],
                "findings": [{"case_id": 9, "relation": "本案对方曾作为本所委托人", "severity": "high"}],
            },
            "duplicate_filing": {
                "blockers": ["同委托人+同对方+同案由的OA在办/待处理案件"],
                "findings": [{"case_id": 11, "relation": "部分当事人重叠", "severity": "review"}],
            },
            "fee_explanation": {"blockers": ["低收费未填理由"]},
            "risk_charge": {"result": "blocked", "issues": ["已超过分段上限"]},
        }
        hard = oa.approval_hard_errors(review)
        self.assertIn("资料不完整: 经办律师", hard)
        self.assertIn("案件分类不是 OA 系统选项", hard)
        self.assertIn("案由不在 OA 字典", hard)
        self.assertIn("委托人与对方同名", hard)
        self.assertIn("同委托人+同对方+同案由的OA在办/待处理案件", hard)
        self.assertIn("低收费未填理由", hard)
        # 风险代理 blocked 不再走硬阻断（转人工）
        self.assertFalse(
            any("超过分段上限" in e for e in hard),
            f"风险代理超上限不应进硬阻断，实际={hard}",
        )
        # conflict/duplicate 的 findings 不入硬阻断
        self.assertFalse(
            any("存在利冲检索命中" in e for e in hard),
            f"利冲线索不应进硬阻断，实际={hard}",
        )
        self.assertFalse(
            any("重叠案件" in e for e in hard),
            f"重复立案线索不应进硬阻断，实际={hard}",
        )

    def test_manual_review_items_list_conflict_and_duplicate_findings(self) -> None:
        """approval_manual_review_items 仅返回 conflict/duplicate 的 findings 与风险代理 blocked。"""
        review = {
            "completeness": {"missing": []},
            "system_options": {"blockers": []},
            "cause": {"blockers": []},
            "conflict": {
                "blockers": [],
                "findings": [
                    {"case_id": 9, "relation": "本案对方曾作为本所委托人", "severity": "high"},
                    {"case_id": 12, "relation": "本案委托人曾作为本所案件对方", "severity": "review"},
                ],
            },
            "duplicate_filing": {
                "blockers": [],
                "findings": [{"case_id": 15, "relation": "部分当事人重叠", "severity": "review"}],
            },
            "fee_explanation": {"blockers": []},
            "risk_charge": {"result": "blocked", "issues": ["缺少标的额"]},
        }
        items = oa.approval_manual_review_items(review)
        kinds = {item["kind"] for item in items}
        self.assertEqual(kinds, {"conflict", "duplicate_filing", "risk_charge"})
        conflict_item = next(i for i in items if i["kind"] == "conflict")
        self.assertIn("2 条利冲检索命中", conflict_item["summary"])
        self.assertIn("高风险 1 条", conflict_item["summary"])
        duplicate_item = next(i for i in items if i["kind"] == "duplicate_filing")
        self.assertIn("1 条当事人/案由重叠", duplicate_item["summary"])
        risk_item = next(i for i in items if i["kind"] == "risk_charge")
        self.assertEqual(risk_item["issues"], ["缺少标的额"])

    def test_prohibited_cause_labor_pay_is_certain_and_hard_blocks(self) -> None:
        """追索劳动报酬案由+风险代理：确定命中87号文第四项，进硬阻断自动驳回。"""
        result = oa.risk_charge_review(
            {"baseTypeName": "民事案件", "chargeMethodName": "风险代理", "chargeAmount": 10000},
            {"chargeMethd": {"Id": 5}, "ChargeMemo": "风险代理，固定收费1万元", "Biaodi": 100000},
            cause_matches=[{
                "name": "追索劳动报酬纠纷",
                "path": "民事案由 > 劳动争议 > 劳动合同纠纷 > 追索劳动报酬纠纷",
            }],
        )
        self.assertEqual(result["result"], "blocked")
        self.assertTrue(result["prohibited_certain"])
        self.assertIn("司发通〔2021〕87号", result["prohibited_certain"][0])
        review = {
            "completeness": {"missing": []}, "system_options": {"blockers": []},
            "cause": {"blockers": []}, "conflict": {"blockers": [], "findings": []},
            "duplicate_filing": {"blockers": [], "findings": []},
            "fee_explanation": {"blockers": []}, "risk_charge": result,
        }
        self.assertTrue(any("禁止风险代理" in e for e in oa.approval_hard_errors(review)))
        # 只有确定禁止项时不再重复产生转人工项
        self.assertEqual(oa.approval_manual_review_items(review), [])

    def test_prohibited_cause_injury_and_marriage_are_certain(self) -> None:
        for name, path in (
            ("工伤保险待遇纠纷", "民事案由 > 劳动争议 > 社会保险纠纷 > 工伤保险待遇纠纷"),
            ("离婚纠纷", "民事案由 > 婚姻家庭、继承纠纷 > 婚姻家庭纠纷 > 离婚纠纷"),
        ):
            certain, hints = oa.risk_prohibited_certain(
                {"baseTypeName": "民事案件"}, [{"name": name, "path": path}]
            )
            self.assertTrue(certain, f"{name} 应确定命中禁止范围")
            self.assertFalse(hints)

    def test_prohibited_case_type_administrative_is_certain(self) -> None:
        """行政案件按案件类别确定禁止，无需案由命中。"""
        certain, _ = oa.risk_prohibited_certain({"baseTypeName": "行政案件"}, [])
        self.assertTrue(certain)
        self.assertIn("行政案件", certain[0])

    def test_labor_branch_without_pay_claim_stays_manual(self) -> None:
        """劳动争议分支但非劳动报酬案由：不确定禁止，转人工核实诉请。"""
        result = oa.risk_charge_review(
            {"baseTypeName": "民事案件", "chargeMethodName": "风险代理", "chargeAmount": 10000},
            {"chargeMethd": {"Id": 5}, "ChargeMemo": "风险代理，固定收费1万元", "Biaodi": 100000},
            cause_matches=[{
                "name": "确认劳动关系纠纷",
                "path": "民事案由 > 劳动争议 > 劳动合同纠纷 > 确认劳动关系纠纷",
            }],
        )
        self.assertEqual(result["prohibited_certain"], [])
        self.assertTrue(any("须合伙人核实诉讼请求" in i for i in result["issues"]))
        review = {
            "completeness": {"missing": []}, "system_options": {"blockers": []},
            "cause": {"blockers": []}, "conflict": {"blockers": [], "findings": []},
            "duplicate_filing": {"blockers": [], "findings": []},
            "fee_explanation": {"blockers": []}, "risk_charge": result,
        }
        self.assertEqual(oa.approval_hard_errors(review), [])
        self.assertEqual({i["kind"] for i in oa.approval_manual_review_items(review)}, {"risk_charge"})

    def test_prohibited_certain_not_waivable_by_risk_reviewed(self) -> None:
        """人工审批勾选「已复核风险收费」也不能放行确定禁止案件。"""
        review = {
            "completeness": {"missing": []}, "system_options": {"blockers": []},
            "cause": {"blockers": []}, "conflict": {"blockers": [], "findings": []},
            "duplicate_filing": {"blockers": [], "findings": []},
            "fee_explanation": {"blockers": []},
            "risk_charge": {
                "result": "blocked",
                "prohibited_certain": ["案由「追索劳动报酬纠纷」属于禁止风险代理的案件范围"],
                "issues": ["案由「追索劳动报酬纠纷」属于禁止风险代理的案件范围"],
            },
        }
        gate = oa.approval_gate_errors(review, risk_reviewed=True)
        self.assertTrue(any("禁止风险代理" in e for e in gate))

    def test_non_risk_charge_ignores_prohibited_cause(self) -> None:
        """非风险代理收费的劳动报酬案件不适用本审查。"""
        result = oa.risk_charge_review(
            {"baseTypeName": "民事案件", "chargeMethodName": "计件收费", "chargeAmount": 5000},
            {"chargeMethd": {"Id": 1}},
            cause_matches=[{"name": "追索劳动报酬纠纷", "path": "民事案由 > 劳动争议"}],
        )
        self.assertEqual(result["result"], "not_applicable")

    def test_manual_review_items_empty_for_clean_review(self) -> None:
        """无线索的干净 review 不应进入转人工列表。"""
        review = {
            "completeness": {"missing": []},
            "system_options": {"blockers": []},
            "cause": {"blockers": []},
            "conflict": {"blockers": [], "findings": []},
            "duplicate_filing": {"blockers": [], "findings": []},
            "fee_explanation": {"blockers": []},
            "risk_charge": {"result": "not_applicable"},
        }
        self.assertEqual(oa.approval_manual_review_items(review), [])

    def test_first_and_second_instance_are_recognized_as_different_stages(self) -> None:
        prior_row = {
            "id": 101,
            "no": "旧案一审",
            "status": 3,
            "statusName": "办理中",
            "baseTypeName": "民事案件",
            "wtrNames": "甲公司",
            "tosNames": "乙公司",
            "causeAction": "合同纠纷",
        }
        prior_detail = {**prior_row, "currentInstanceId": 31, "currentInstanceName": "一审"}
        current_detail = {
            "id": 202,
            "baseTypeName": "民事案件",
            "currentInstanceId": 32,
            "currentInstanceName": "二审",
            "wtrNames": "甲公司",
            "tosNames": "乙公司",
            "causeAction": "合同纠纷",
        }
        with patch("app.oa.get_case_list_all", return_value=[prior_row]), patch(
            "app.oa.get_case_detail", return_value=prior_detail
        ):
            result = oa.duplicate_filing_review(
                "https://example.invalid", "token", current_detail, 202
            )

        self.assertEqual(result["result"], "related_stage_match")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["findings"], [])
        self.assertEqual(len(result["informational"]), 1)
        self.assertIn("一审", result["informational"][0]["relation"])
        self.assertIn("二审", result["informational"][0]["relation"])

    def test_civil_and_execution_cases_are_recognized_as_different_proceedings(self) -> None:
        prior_row = {
            "id": 102,
            "no": "旧案一审",
            "status": 3,
            "statusName": "办理中",
            "baseTypeName": "民事案件",
            "wtrNames": "甲公司",
            "tosNames": "乙公司",
            "causeAction": "合同纠纷",
        }
        prior_detail = {**prior_row, "currentInstanceId": 31, "currentInstanceName": "一审"}
        current_detail = {
            "id": 203,
            "baseTypeName": "执行案件",
            "currentInstanceId": 71,
            "currentInstanceName": "执行",
            "wtrNames": "甲公司",
            "tosNames": "乙公司",
            "causeAction": "合同纠纷",
        }
        with patch("app.oa.get_case_list_all", return_value=[prior_row]), patch(
            "app.oa.get_case_detail", return_value=prior_detail
        ):
            result = oa.duplicate_filing_review(
                "https://example.invalid", "token", current_detail, 203
            )

        self.assertEqual(result["result"], "related_stage_match")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["findings"], [])
        self.assertEqual(len(result["informational"]), 1)
        self.assertIn("民事案件", result["informational"][0]["relation"])
        self.assertIn("执行案件", result["informational"][0]["relation"])

    def test_same_stage_party_and_cause_match_requires_review_not_auto_reject(self) -> None:
        prior_row = {
            "id": 103,
            "no": "旧案一审",
            "status": 3,
            "statusName": "办理中",
            "baseTypeName": "民事案件",
            "wtrNames": "甲公司",
            "tosNames": "乙公司",
            "causeAction": "合同纠纷",
        }
        prior_detail = {**prior_row, "currentInstanceId": 31, "currentInstanceName": "一审"}
        current_detail = {
            "id": 204,
            "baseTypeName": "民事案件",
            "currentInstanceId": 31,
            "currentInstanceName": "一审",
            "wtrNames": "甲公司",
            "tosNames": "乙公司",
            "causeAction": "合同纠纷",
        }
        with patch("app.oa.get_case_list_all", return_value=[prior_row]), patch(
            "app.oa.get_case_detail", return_value=prior_detail
        ):
            result = oa.duplicate_filing_review(
                "https://example.invalid", "token", current_detail, 204
            )

        self.assertEqual(result["result"], "manual_review_required")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["severity"], "review")

    def test_same_principal_and_cause_with_different_opponent_is_informational(self) -> None:
        prior_row = {
            "id": 104,
            "no": "历史案一审",
            "status": 3,
            "statusName": "办理中",
            "baseTypeName": "民事案件",
            "wtrNames": "甲公司",
            "tosNames": "丙公司",
            "causeAction": "买卖合同纠纷",
        }
        current_detail = {
            "id": 205,
            "baseTypeName": "民事案件",
            "wtrNames": "甲公司",
            "tosNames": "乙公司",
            "causeAction": "买卖合同纠纷",
        }
        with patch("app.oa.get_case_list_all", return_value=[prior_row]):
            result = oa.duplicate_filing_review(
                "https://example.invalid", "token", current_detail, 205
            )

        self.assertEqual(result["result"], "related_stage_match")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["findings"], [])
        self.assertEqual(len(result["informational"]), 1)
        self.assertEqual(result["informational"][0]["severity"], "info")

    def test_archived_same_parties_with_different_cause_is_informational(self) -> None:
        prior_row = {
            "id": 105,
            "no": "已归档历史案",
            "status": 99,
            "statusName": "已归档",
            "baseTypeName": "民事案件",
            "wtrNames": "甲公司",
            "tosNames": "乙公司",
            "causeAction": "借款合同纠纷",
        }
        current_detail = {
            "id": 206,
            "baseTypeName": "民事案件",
            "wtrNames": "甲公司",
            "tosNames": "乙公司",
            "causeAction": "买卖合同纠纷",
        }
        with patch("app.oa.get_case_list_all", return_value=[prior_row]):
            result = oa.duplicate_filing_review(
                "https://example.invalid", "token", current_detail, 206
            )

        self.assertEqual(result["result"], "related_stage_match")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["findings"], [])
        self.assertEqual(len(result["informational"]), 1)
        self.assertEqual(result["informational"][0]["severity"], "info")


    def test_arbitration_institution_uses_real_oa_field(self) -> None:
        """仲裁机构应读取 OA entity 的 Zhongcai，
        旧的 arbitrationInstitution/arbitrationCommission/courtName 是盲猜。"""
        result = oa.completeness_review(
            {
                "baseTypeName": "仲裁业务", "causeAction": "合同纠纷",
                "chargeMethodName": "计件收费", "chargeAmount": 5000,
                "clients": [{"roleType": 0, "name": "甲"}, {"roleType": 1, "name": "乙"}],
                "instances": [{"id": 1, "roles": [{"id": 1}]}],
            },
            {"Zhongcai": "温州仲裁委员会"},
        )
        self.assertNotIn("仲裁机构", result["missing"])

        # 真实字段缺失时必须如实报告
        result = oa.completeness_review(
            {
                "baseTypeName": "仲裁业务", "causeAction": "合同纠纷",
                "chargeMethodName": "计件收费", "chargeAmount": 5000,
                "clients": [{"roleType": 0, "name": "甲"}, {"roleType": 1, "name": "乙"}],
                "instances": [{"id": 1, "roles": [{"id": 1}]}],
            },
            {},
        )
        self.assertIn("仲裁机构", result["missing"])

    def test_bankruptcy_client_role_uses_weituo_buchong(self) -> None:
        """破产案件（诉讼）的委托人身份应读取 OA entity 的 WeituoBuchong，
        旧的 clientRole/partyRole/WTQXContent 是盲猜。"""
        result = oa.completeness_review(
            {
                "baseTypeName": "破产诉讼案件", "causeAction": "破产清算",
                "chargeMethodName": "计件收费", "chargeAmount": 0,
                "clients": [{"roleType": 0, "name": "甲公司"}],
                "instances": [{"id": 1, "roles": [{"id": 1}]}],
            },
            {"WeituoBuchong": "破产清算"},
        )
        self.assertNotIn("委托人身份", result["missing"])

    def test_execution_subject_amount_uses_biaodi_only(self) -> None:
        """执行案件标的额应读取 OA entity 的 Biaodi，
        旧的 biaodi/executionAmount 是盲猜（小写 biaodi OA 真实返回的是大写）。"""
        # Biaodi 存在 → 不报缺失
        result = oa.completeness_review(
            {
                "baseTypeName": "执行案件", "causeAction": "合同纠纷",
                "chargeMethodName": "计件收费", "chargeAmount": 5000,
                "clients": [{"roleType": 0, "name": "甲"}],
                "instances": [{"id": 1, "roles": [{"id": 1}]}],
            },
            {"Biaodi": 100000, "ChargeMemo": "无金额事项说明"},
        )
        self.assertNotIn("申请执行金额或无金额事项具体说明", result["missing"])

        # Biaodi 缺失 + 无说明 → 必须报缺失
        result = oa.completeness_review(
            {
                "baseTypeName": "执行案件", "causeAction": "合同纠纷",
                "chargeMethodName": "计件收费", "chargeAmount": 5000,
                "clients": [{"roleType": 0, "name": "甲"}],
                "instances": [{"id": 1, "roles": [{"id": 1}]}],
            },
            {},
        )
        self.assertIn("申请执行金额或无金额事项具体说明", result["missing"])


    def test_advisor_dates_use_real_oa_field_names(self) -> None:
        """顾问开始/结束日期应读取 OA entity 的 GW_StartDate / GW_EndDate，
        旧的 serviceStartDate/GuWenStartDate 等候选名是盲猜，不会命中真实数据。"""
        # 关键断言：GW_StartDate / GW_EndDate 是真实 OA 字段，必须能命中
        result = oa.completeness_review(
            {"baseTypeName": "顾问签约", "chargeMethodName": "计件收费", "chargeAmount": 10000},
            {"GW_StartDate": "2024-01-01", "GW_EndDate": "2024-12-31"},
            non_litigation=True,
        )
        self.assertNotIn(
            "顾问开始日期", result["missing"],
            f"GW_StartDate 未被读取，候选字段名可能再次漂移。result={result}",
        )
        self.assertNotIn(
            "顾问结束日期", result["missing"],
            f"GW_EndDate 未被读取，候选字段名可能再次漂移。result={result}",
        )

        # 真实字段缺失时必须如实报告（防止再次盲猜回退或硬编码假值）
        result = oa.completeness_review(
            {"baseTypeName": "顾问签约", "chargeMethodName": "计件收费", "chargeAmount": 10000},
            {},
            non_litigation=True,
        )
        self.assertIn("顾问开始日期", result["missing"])
        self.assertIn("顾问结束日期", result["missing"])


if __name__ == "__main__":
    unittest.main()
