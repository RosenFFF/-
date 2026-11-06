"""加密文件存储：原件与渲染页都只存 AES-256-GCM 密文，路径只由 UUID 决定。"""

from __future__ import annotations

import os
from pathlib import Path

from app.core import crypto
from app.core.config import Settings


class EncryptedStore:
    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.storage_dir)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.keks = {settings.data_kek_id: settings.kek_bytes}
        self.kek_id = settings.data_kek_id

    def _path(self, doc_id: str, name: str) -> Path:
        # doc_id 为服务端生成的 UUID，name 为固定常量，不受用户输入影响
        return self.root / doc_id / name

    def new_wrapped_dek(self, doc_id: str) -> tuple[bytes, str]:
        dek = crypto.new_dek()
        return dek, crypto.wrap_dek(self.keks[self.kek_id], self.kek_id, dek, doc_id.encode())

    def dek(self, doc_id: str, wrapped: str) -> bytes:
        return crypto.unwrap_dek(self.keks, wrapped, doc_id.encode())

    def put(self, doc_id: str, name: str, dek: bytes, data: bytes) -> None:
        p = self._path(doc_id, name)
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(crypto.encrypt(dek, data, f"{doc_id}/{name}".encode()))
        os.replace(tmp, p)

    def get(self, doc_id: str, name: str, dek: bytes) -> bytes:
        blob = self._path(doc_id, name).read_bytes()
        return crypto.decrypt(dek, blob, f"{doc_id}/{name}".encode())

    def exists(self, doc_id: str, name: str) -> bool:
        return self._path(doc_id, name).exists()

    def delete(self, doc_id: str) -> None:
        d = self.root / doc_id
        if d.is_dir():
            for f in d.iterdir():
                f.unlink(missing_ok=True)
            d.rmdir()
