"""信封加密：每个文件一个随机数据密钥（DEK），DEK 用主密钥（KEK）包裹后入库。

存储格式：nonce(12) || ciphertext+tag。包裹后的 DEK 格式：kek_id ":" base64(nonce || wrapped)。
关联数据（AAD）绑定 document_id，防止密文被挪到别的记录下解密。
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE = 12


def new_dek() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:NONCE], blob[NONCE:], aad)


def wrap_dek(kek: bytes, kek_id: str, dek: bytes, aad: bytes) -> str:
    return f"{kek_id}:{base64.b64encode(encrypt(kek, dek, aad)).decode()}"


def unwrap_dek(keks: dict[str, bytes], wrapped: str, aad: bytes) -> bytes:
    kek_id, b64 = wrapped.split(":", 1)
    return decrypt(keks[kek_id], base64.b64decode(b64), aad)
