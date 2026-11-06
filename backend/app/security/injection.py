"""Heuristic input guard, not a claim of complete prompt-injection prevention."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?)",
    r"(?:reveal|print|show|repeat|extract)\b.{0,30}(?:system\s+prompt|api\s*key|secret)",
    r"(?:you are now|act as)\s+(?:DAN|an?\s+unrestricted|system|developer)",
    r"(?:忽略|无视|忘记).{0,12}(?:指令|提示|规则)|(?:泄露|输出|显示).{0,12}(?:系统提示|密钥)",
    r"<\|(?:im_start|system|endoftext)\|>|\[INST\]|(?:^|\n)\s*(?:system|developer)\s*:",
    r"(?:base64|rot13).{0,30}(?:decode|execute|解码|执行)|jailbreak",
]


@dataclass(slots=True)
class InjectionResult:
    detected: bool
    text: str
    patterns: list[str]


def inspect(text: str) -> InjectionResult:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    hits = [str(i) for i, p in enumerate(_PATTERNS) if re.search(p, text, re.I)]
    # Fail closed for the whole data region, rather than leaving a split malicious instruction.
    return InjectionResult(bool(hits), "[CONTENT BLOCKED: suspected prompt injection]" if hits else text, hits)
