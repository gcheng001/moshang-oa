"""Operating-system credential storage for remembered OA logins.

This module deliberately has no plaintext fallback. A user can always use a
one-session login, but long-running approval automation requires an OS vault.
"""

from __future__ import annotations

from dataclasses import dataclass

SERVICE_NAME = "办公助手.OA"
LAST_ACCOUNT_KEY = "__last_account__"
FEISHU_SERVICE_NAME = "办公助手.飞书机器人"
FEISHU_WEBHOOK_KEY = "webhook"


class CredentialStoreUnavailable(RuntimeError):
    """Raised when the operating-system credential store cannot be used."""


def _keyring():
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError as exc:
        raise CredentialStoreUnavailable("系统凭据库组件不可用") from exc
    return keyring, KeyringError


def save_password(username: str, password: str) -> None:
    keyring, keyring_error = _keyring()
    try:
        keyring.set_password(SERVICE_NAME, username, password)
        keyring.set_password(SERVICE_NAME, LAST_ACCOUNT_KEY, username)
    except keyring_error as exc:
        raise CredentialStoreUnavailable("无法写入系统凭据库") from exc


@dataclass(frozen=True)
class SavedLogin:
    username: str
    password: str


def load_last_login() -> SavedLogin | None:
    keyring, keyring_error = _keyring()
    try:
        username = keyring.get_password(SERVICE_NAME, LAST_ACCOUNT_KEY)
        if not username:
            return None
        password = keyring.get_password(SERVICE_NAME, username)
    except keyring_error as exc:
        raise CredentialStoreUnavailable("无法读取系统凭据库") from exc
    if not password:
        return None
    return SavedLogin(username=username, password=password)


def has_password(username: str) -> bool:
    """Whether this specific account has opted into OS-vault persistence."""
    keyring, keyring_error = _keyring()
    try:
        return bool(keyring.get_password(SERVICE_NAME, username))
    except keyring_error as exc:
        raise CredentialStoreUnavailable("无法读取系统凭据库") from exc


def forget_password(username: str) -> None:
    keyring, keyring_error = _keyring()
    try:
        if keyring.get_password(SERVICE_NAME, username) is not None:
            keyring.delete_password(SERVICE_NAME, username)
        if keyring.get_password(SERVICE_NAME, LAST_ACCOUNT_KEY) == username:
            keyring.delete_password(SERVICE_NAME, LAST_ACCOUNT_KEY)
    except keyring_error as exc:
        raise CredentialStoreUnavailable("无法清除系统凭据库") from exc


def forget_last_login() -> None:
    """Forget whichever account is currently selected for automatic restore."""
    saved = load_last_login()
    if saved is not None:
        forget_password(saved.username)


def save_feishu_webhook(webhook: str) -> None:
    keyring, keyring_error = _keyring()
    try:
        if webhook.strip():
            keyring.set_password(FEISHU_SERVICE_NAME, FEISHU_WEBHOOK_KEY, webhook.strip())
        elif keyring.get_password(FEISHU_SERVICE_NAME, FEISHU_WEBHOOK_KEY) is not None:
            keyring.delete_password(FEISHU_SERVICE_NAME, FEISHU_WEBHOOK_KEY)
    except keyring_error as exc:
        raise CredentialStoreUnavailable("无法写入飞书机器人密钥") from exc


def load_feishu_webhook() -> str | None:
    keyring, keyring_error = _keyring()
    try:
        return keyring.get_password(FEISHU_SERVICE_NAME, FEISHU_WEBHOOK_KEY)
    except keyring_error as exc:
        raise CredentialStoreUnavailable("无法读取飞书机器人密钥") from exc
