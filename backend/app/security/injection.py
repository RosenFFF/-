"""Heuristic input guard, not a claim of complete prompt-injection prevention."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass

_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?)",
    r"(?:reveal|print|show|repeat|extract)\b.{0,30}(?:system\s+prompt|api\s*key|secret)",
    r"(?:you are now|act as)\s+(?:DAN|an?\s+unrestricted|system|developer)",
    r"(?:忽略|无视|忘记).{0,12}(?:指令|提示|规则)|(?:泄露|输出|显示).{0,12}(?:系统提示|密钥)",
    r"<\|(?:im_start|system|endoftext)\|>|\[INST\]|(?:^|\n)\s*(?:system|developer)\s*:",
    r"(?:override|disregard|forget)\b.{0,24}(?:instructions?|prompts?|polic(?:y|ies))",
    r"(?:disable|bypass|turn off)\b.{0,24}(?:auth(?:entication|orization)?|audit|logging|permissions?|safety)",
    r"(?:关闭|禁用|绕过).{0,12}(?:鉴权|权限|审计|安全|日志)",
    r"<\s*/?\s*(?:system|developer|assistant)\s*>|\[(?:SYSTEM|DEVELOPER)\]",
    r"(?:base64|rot13).{0,30}(?:decode|execute|解码|执行)|jailbreak",
]


@dataclass(slots=True)
class InjectionResult:
    detected: bool
    text: str
    patterns: list[str]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", html.unescape(text))
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


def inspect(text: str) -> InjectionResult:
    text = normalize(text)
    hits = [str(i) for i, p in enumerate(_PATTERNS) if re.search(p, text, re.I)]
    # Fail closed for the whole data region, rather than leaving a split malicious instruction.
    return InjectionResult(bool(hits), "[CONTENT BLOCKED: suspected prompt injection]" if hits else text, hits)


def out_of_scope(text: str) -> bool:
    return bool(
        re.search(
            r"(?:other|another)\s+(?:users?|tenants?|reviews?|accounts?)|"
            r"(?:其他|别的|别人的|其它).{0,8}(?:用户|租户|审查|账号|报告)|"
            r"(?:bypass|绕过).{0,20}(?:auth|permission|权限|鉴权)",
            text,
            re.I,
        )
    )


def inspect_data(value) -> InjectionResult:
    """Inspect strings as actual data, not JSON-escaped representations hiding role boundaries."""

    def strings(v):
        if isinstance(v, dict):
            for key, item in v.items():
                yield str(key)
                yield from strings(item)
        elif isinstance(v, (list, tuple)):
            for item in v:
                yield from strings(item)
        elif isinstance(v, str):
            yield v

    return inspect("\n".join(strings(value)))
