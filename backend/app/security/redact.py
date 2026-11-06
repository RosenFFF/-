"""Conservative, deterministic outbound PII masking. Mapping is task-local only."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# Priority prevents a bank/id sequence from being interpreted as a phone number.
_PATTERNS = [
    ("address", "ADDRESS", re.compile(r'(?i)(?<="address": ")[^"\n]{1,200}')),
    ("person_name", "PERSON", re.compile(r'(?i)(?<="person_name": ")[^"\n]{1,100}')),
    ("id_number", "ID", re.compile(r'(?i)(?<="id_number": ")[^"\n]{1,100}')),
    ("phone", "PHONE", re.compile(r'(?i)(?<="phone": ")[^"\n]{1,100}')),
    ("bank_account", "BANK", re.compile(r'(?i)(?<="bank_account": ")[^"\n]{1,100}')),
    ("email", "EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("id_number", "ID", re.compile(r"(?<![\w])\d{17}[\dXx](?!\w)|(?i:(?<=passport: ))[A-Z0-9]{6,12}")),
    ("bank_account", "BANK", re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")),
    ("phone", "PHONE", re.compile(r"(?<![\w])(?:\+\d{1,3}[ -]?)?(?:1[3-9]\d{9}|\(?\d{3}\)?[ -]\d{3}[ -]\d{4})(?!\d)")),
    ("address", "ADDRESS", re.compile(r"(?im)(?:(?<=address: )|(?<=地址：)|(?<=地址: ))[^\n;]{4,200}")),
    ("address", "ADDRESS", re.compile(r"\d{1,5}\s+[A-Za-z0-9 .-]{2,70}\s(?:Street|Road|Avenue|Lane|Blvd)\b", re.I)),
    ("person_name", "PERSON", re.compile(r"(?im)(?:(?<=contact: )|(?<=联系人：))[^\n;]{2,60}")),
]


@dataclass(slots=True)
class MaskResult:
    text: str
    mapping: dict[str, str]
    counts: dict[str, int]

    def restore(self, text: str) -> str:
        return restore(text, self.mapping)


def mask(text: str) -> MaskResult:
    mapping: dict[str, str] = {}
    counts: Counter = Counter()
    seen: dict[tuple[str, str], str] = {}
    # Escape user-supplied placeholders; they must not impersonate ones we generated.
    text = re.sub(r"<(PHONE|EMAIL|BANK|ID|ADDRESS|PERSON)_\d+>", "[untrusted-placeholder]", text)
    for kind, prefix, pattern in _PATTERNS:

        def replace(m: re.Match, kind=kind, prefix=prefix) -> str:
            raw = m.group()
            pair = (kind, raw)
            counts[kind] += 1
            if pair not in seen:
                token = f"<{prefix}_{len([k for k in mapping if k.startswith('<' + prefix + '_')]) + 1}>"
                seen[pair] = token
                mapping[token] = raw
            return seen[pair]

        text = pattern.sub(replace, text)
    return MaskResult(text, mapping, dict(counts))


def restore(text: str, mapping: dict[str, str]) -> str:
    return re.sub(r"<(?:PHONE|EMAIL|BANK|ID|ADDRESS|PERSON)_\d+>", lambda m: mapping.get(m.group(), m.group()), text)


def public_value(value: str | None) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    result = mask(value)
    return result.text, bool(result.counts)
