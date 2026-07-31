from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import credential_handoff, credentials, main, oa, sessions


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


class AuthAndPermissionTests(unittest.TestCase):
    def test_credential_handoff_is_encrypted_and_round_trips(self) -> None:
        fake = FakeKeyring()
        with patch("app.credentials._keyring", return_value=(fake, RuntimeError)):
            credentials.save_password("lawyer", "top-secret")
            credentials.save_feishu_webhook("https://open.feishu.cn/open-apis/bot/v2/hook/example")
            code, bundle = credential_handoff.export_bundle()
            self.assertNotIn("top-secret", bundle)
            credentials.forget_password("lawyer")
            credentials.save_feishu_webhook("")
            username = credential_handoff.import_bundle(bundle, code)
            self.assertEqual(username, "lawyer")
            self.assertEqual(credentials.load_last_login().password, "top-secret")
            self.assertTrue(credentials.load_feishu_webhook())

    def test_approval_permission_matches_oa_initiate_approve_menu(self) -> None:
        self.assertTrue(oa.has_filing_approval_permission({"MenuPermissions": {"LawcaseList1": None}}))
        self.assertTrue(oa.has_filing_approval_permission({"IsAdmin": True, "MenuPermissions": {}}))
        self.assertFalse(oa.has_filing_approval_permission({"MenuPermissions": {"LawcaseList": None}}))
        self.assertFalse(oa.has_filing_approval_permission({"MenuPermissions": {"LawcaseList3": None}}))

    def test_remembered_password_stays_in_credential_store(self) -> None:
        fake = FakeKeyring()
        with patch("app.credentials._keyring", return_value=(fake, RuntimeError)):
            credentials.save_password("lawyer", "not-in-browser")
            self.assertEqual(credentials.load_last_login(), credentials.SavedLogin("lawyer", "not-in-browser"))
            credentials.forget_password("lawyer")
            self.assertIsNone(credentials.load_last_login())

    def test_approval_guard_rejects_a_non_approver(self) -> None:
        session = sessions.Session(
            username="lawyer",
            password="only-in-memory",
            base_url="https://example.invalid",
            token="token",
            profile={},
            can_approve=False,
        )
        with self.assertRaises(HTTPException) as caught:
            main.require_approval_session(session)
        self.assertEqual(caught.exception.status_code, 403)

    def test_criminal_case_completeness_does_not_require_opponent(self) -> None:
        detail = {
            "baseTypeName": "刑事",
            "clients": [{"roleType": 0, "name": "张三"}],
            "empNames": "李律师",
            "causeAction": "盗窃罪",
            "instances": "一审",
            "chargeAmount": 8000,
        }
        entity = {"chargeMethd": "固定收费"}

        review = oa.completeness_review(detail, entity, criminal_case=oa.is_criminal_case(detail))

        self.assertEqual(review["result"], "complete")
        self.assertNotIn("对方", review["missing"])
        self.assertTrue(review["criminal_case"])

    def test_criminal_legal_aid_case_uses_charge_to_identify_case_type(self) -> None:
        detail = {
            "baseTypeName": "公益法律",
            "caseCategoryName": None,
            "clients": [{"roleType": 0, "name": "张三"}],
            "empNames": "李律师",
            "causeAction": "引诱、容留、介绍卖淫罪",
            "chargeAmount": 0,
        }
        entity = {"chargeMethd": "免费"}

        review = oa.completeness_review(
            detail,
            entity,
            non_litigation=oa.is_non_litigation(detail),
            criminal_case=oa.is_criminal_case(detail),
        )

        self.assertEqual(review["result"], "complete")
        self.assertNotIn("对方", review["missing"])
        self.assertTrue(review["criminal_case"])

    def test_civil_case_completeness_still_requires_opponent(self) -> None:
        detail = {
            "baseTypeName": "民事",
            "clients": [{"roleType": 0, "name": "张三"}],
            "empNames": "李律师",
            "causeAction": "民间借贷纠纷",
            "instances": "一审",
            "chargeAmount": 8000,
        }
        entity = {"chargeMethd": "固定收费"}

        review = oa.completeness_review(detail, entity, criminal_case=oa.is_criminal_case(detail))

        self.assertEqual(review["result"], "blocked")
        self.assertIn("对方", review["missing"])
        self.assertFalse(review["criminal_case"])


if __name__ == "__main__":
    unittest.main()
