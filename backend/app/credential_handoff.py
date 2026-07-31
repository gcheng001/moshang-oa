"""One-time encrypted transfer for OA and optional Feishu credentials."""

from __future__ import annotations

import base64
import json
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import credentials

AAD = "办公助手凭据迁移-v1".encode("utf-8")


def _key(code: str, salt: bytes) -> bytes:
    normalized = "".join(code.upper().split()).encode("ascii")
    if len(normalized) < 10:
        raise ValueError("迁移码不正确")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(normalized)


def export_bundle() -> tuple[str, str]:
    saved = credentials.load_last_login()
    if saved is None:
        raise ValueError("没有已保存的 OA 登录凭据，请先勾选保持登录")
    code = secrets.token_hex(6).upper()
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    payload = json.dumps(
        {
            "version": 1,
            "username": saved.username,
            "password": saved.password,
            "feishu_webhook": credentials.load_feishu_webhook(),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    ciphertext = AESGCM(_key(code, salt)).encrypt(nonce, payload, AAD)
    envelope = {
        "version": 1,
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }
    return code, base64.b64encode(json.dumps(envelope).encode()).decode()


def import_bundle(encoded: str, code: str) -> str:
    try:
        envelope = json.loads(base64.b64decode(encoded))
        salt = base64.b64decode(envelope["salt"])
        nonce = base64.b64decode(envelope["nonce"])
        ciphertext = base64.b64decode(envelope["ciphertext"])
        clear = AESGCM(_key(code, salt)).decrypt(nonce, ciphertext, AAD)
        payload = json.loads(clear)
        username = str(payload["username"])
        password = str(payload["password"])
    except Exception as exc:
        raise ValueError("迁移文件或迁移码不正确，未写入任何凭据") from exc
    credentials.save_password(username, password)
    credentials.save_feishu_webhook(str(payload.get("feishu_webhook") or ""))
    return username
