from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import automation, credentials, local_server, main, sessions


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def approval_session() -> sessions.Session:
    return sessions.Session(
        username="lawyer",
        password="secret",
        base_url="https://example.invalid",
        token="token",
        profile={"userName": "lawyer", "employeeName": "测试律师"},
        can_approve=True,
    )


def passing_review() -> dict:
    return {
        "completeness": {"missing": []},
        "cause": {"blockers": []},
        "conflict": {"blockers": [], "findings": [], "principals": [], "opponents": []},
        "duplicate_filing": {"blockers": [], "findings": []},
        "fee_explanation": {"blockers": []},
        "risk_charge": {"result": "preliminary_pass"},
    }


class SessionRegressionTests(unittest.TestCase):
    def tearDown(self) -> None:
        with sessions._lock:
            sessions._sessions.clear()

    def test_current_user_reuses_an_existing_one_session_login(self) -> None:
        session = approval_session()
        with sessions._lock:
            sessions._sessions["active"] = session

        payload = main.api_current_user(session)

        self.assertEqual(payload["userName"], "lawyer")
        self.assertTrue(payload["canApprove"])

    def test_unchecked_remember_removes_an_older_password_for_same_account(self) -> None:
        fake = FakeKeyring()
        session = approval_session()
        with patch("app.credentials._keyring", return_value=(fake, RuntimeError)):
            credentials.save_password("lawyer", "old-secret")
            with patch("app.sessions._create", return_value=("session-id", session)):
                sessions.create(session.base_url, "lawyer", "new-secret", remember=False)
            self.assertIsNone(credentials.load_last_login())

    def test_logout_with_a_stale_session_id_still_forgets_last_login(self) -> None:
        fake = FakeKeyring()
        with patch("app.credentials._keyring", return_value=(fake, RuntimeError)):
            credentials.save_password("lawyer", "secret")
            self.assertEqual(main.api_logout("stale-session"), {"ok": True})
            self.assertIsNone(credentials.load_last_login())


class AutomationRegressionTests(unittest.TestCase):
    def test_rejection_fingerprint_is_scoped_to_case_and_relevant_evidence(self) -> None:
        review = passing_review()
        review["conflict"] = {
            "blockers": ["存在明确利冲"],
            "findings": [{"case_id": 9, "relation": "不利方"}],
            "principals": ["甲公司"],
            "opponents": ["乙公司"],
        }

        first = automation._reject_fingerprint(review, 100)
        same = automation._reject_fingerprint(review, 100)
        other_case = automation._reject_fingerprint(review, 101)

        self.assertEqual(first, same)
        self.assertNotEqual(first[0], other_case[0])

    def test_overlapping_checks_are_rejected_instead_of_writing_twice(self) -> None:
        self.assertTrue(automation._run_lock.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(ValueError, "正在进行"):
                automation.run_once(approval_session())
        finally:
            automation._run_lock.release()

    def test_disabling_during_review_stops_before_oa_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            automation, "STATE_DIR", Path(temp_dir)
        ), patch.object(automation, "STATE_FILE", Path(temp_dir) / "state.json"), patch.object(
            automation, "_shadow_remaining", return_value=0
        ):
            session = approval_session()
            automation._write(
                {
                    "version": 1,
                    "accounts": {session.username: {"enabled": True, "shadow_started_at": "2020-01-01T00:00:00+00:00"}},
                }
            )

            def disable_then_return_review(*_args, **_kwargs):
                automation.set_enabled(session, False)
                return passing_review()

            with patch("app.automation.oa.get_case_list", return_value={"data": [{"id": 1}]}), patch(
                "app.automation.oa.get_case_detail", return_value={"id": 1, "status": 1, "preNo": "测-1"}
            ), patch("app.automation.oa.build_approval_review", side_effect=disable_then_return_review), patch(
                "app.automation.oa.post_lian_approval"
            ) as post:
                result = automation.run_once(session)

            post.assert_not_called()
            self.assertEqual(result["results"][0]["kind"], "automation_stopped")

    def test_status_is_read_again_immediately_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            automation, "STATE_DIR", Path(temp_dir)
        ), patch.object(automation, "STATE_FILE", Path(temp_dir) / "state.json"), patch.object(
            automation, "_shadow_remaining", return_value=0
        ):
            session = approval_session()
            automation._write(
                {
                    "version": 1,
                    "accounts": {session.username: {"enabled": True, "shadow_started_at": "2020-01-01T00:00:00+00:00"}},
                }
            )
            details = [
                {"id": 1, "status": 1, "statusName": "立案待审", "preNo": "测-1"},
                {"id": 1, "status": 3, "statusName": "已立案", "preNo": "测-1"},
            ]
            with patch("app.automation.oa.get_case_list", return_value={"data": [{"id": 1}]}), patch(
                "app.automation.oa.get_case_detail", side_effect=details
            ), patch("app.automation.oa.build_approval_review", return_value=passing_review()), patch(
                "app.automation.oa.post_lian_approval"
            ) as post:
                result = automation.run_once(session)

            post.assert_not_called()
            self.assertEqual(result["results"][0]["kind"], "status_changed")

    def test_review_change_during_check_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            automation, "STATE_DIR", Path(temp_dir)
        ), patch.object(automation, "STATE_FILE", Path(temp_dir) / "state.json"), patch.object(
            automation, "_shadow_remaining", return_value=0
        ):
            session = approval_session()
            automation._write(
                {
                    "version": 1,
                    "accounts": {session.username: {"enabled": True, "shadow_started_at": "2020-01-01T00:00:00+00:00"}},
                }
            )
            changed = passing_review()
            changed["completeness"] = {"missing": ["委托人"]}
            with patch("app.automation.oa.get_case_list", return_value={"data": [{"id": 1}]}), patch(
                "app.automation.oa.get_case_detail",
                return_value={"id": 1, "status": 1, "statusName": "立案待审", "preNo": "测-1"},
            ), patch(
                "app.automation.oa.build_approval_review", side_effect=[passing_review(), changed]
            ), patch("app.automation.oa.post_lian_approval") as post:
                result = automation.run_once(session)

            post.assert_not_called()
            self.assertEqual(result["results"][0]["kind"], "review_changed")


class LocalServerIdentityTests(unittest.TestCase):
    def test_health_probe_rejects_an_unrelated_local_service(self) -> None:
        wrong = io.BytesIO(json.dumps({"app": "something-else", "version": "1"}).encode())
        with patch("app.local_server.urlopen", return_value=wrong):
            self.assertFalse(local_server.is_expected_backend("127.0.0.1", 8017))

    def test_health_probe_accepts_only_the_current_app_version(self) -> None:
        expected = io.BytesIO(
            json.dumps({"app": local_server.APP_ID, "version": local_server.APP_VERSION}).encode()
        )
        with patch("app.local_server.urlopen", return_value=expected):
            self.assertTrue(local_server.is_expected_backend("127.0.0.1", 8017))


if __name__ == "__main__":
    unittest.main()
