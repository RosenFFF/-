import os

import pytest
from cryptography.exceptions import InvalidTag

from app.audit.service import mask_ip
from app.core import crypto
from app.services.files import clean_filename


def test_envelope_roundtrip_and_aad_binding():
    kek, dek = os.urandom(32), crypto.new_dek()
    wrapped = crypto.wrap_dek(kek, "k1", dek, b"doc-a")
    assert crypto.unwrap_dek({"k1": kek}, wrapped, b"doc-a") == dek
    with pytest.raises(InvalidTag):
        crypto.unwrap_dek({"k1": kek}, wrapped, b"doc-b")  # 密文挪到别的记录下无法解密
    blob = crypto.encrypt(dek, b"secret", b"x")
    with pytest.raises(InvalidTag):
        crypto.decrypt(dek, blob[:-1] + bytes([blob[-1] ^ 1]), b"x")


@pytest.mark.parametrize(("ip", "expected"), [("203.0.113.7", "203.0.113.*"), ("not-an-ip", None), (None, None)])
def test_mask_ip(ip, expected):
    assert mask_ip(ip) == expected


def test_clean_filename():
    assert clean_filename("..\\..\\a\x07b.pdf") == "ab.pdf"
    assert clean_filename("") == "document"
    assert len(clean_filename("a" * 500)) == 120
