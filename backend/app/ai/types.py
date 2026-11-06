"""Validated internal model outputs, distinct from the public API representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.provenance import provenance


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


FieldKey = Literal[
    "invoice_no",
    "hs_code",
    "total_amount",
    "currency",
    "origin_country",
    "consignee",
    "quantity",
    "unit_price",
    "goods_description",
    "certificate_no",
    "declaration_no",
    "bill_no",
    "gross_weight",
    "packages",
    "email",
    "phone",
    "bank_account",
    "address",
]


class FieldValue(StrictModel):
    key: FieldKey
    value: str | None = Field(max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class Extraction(StrictModel):
    fields: list[FieldValue] = Field(max_length=40)


class ReasonedFinding(StrictModel):
    severity: Literal["info", "low", "medium", "high"]
    category: Literal[
        "missing_field",
        "inconsistency",
        "classification",
        "origin",
        "restricted_goods",
        "sanctions",
        "valuation",
        "format",
        "other",
    ]
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=3000)
    rule_ids: list[str] = Field(max_length=10)
    field_keys: list[FieldKey] = Field(default_factory=list, max_length=20)
    suggestion: str | None = Field(default=None, max_length=2000)


class Reasoning(StrictModel):
    summary: str = Field(min_length=1, max_length=3000)
    findings: list[ReasonedFinding] = Field(max_length=30)


@dataclass
class LLMResult:
    value: Any  # instance of requested Pydantic schema, or None for explicit rules fallback
    traces: list[dict]
    degrade_level: str


def trace(category: str, model: str, task: str, ms: int, *, provider="local", status="ok", **kw) -> dict:
    return {
        "category": category,
        "provider": provider,
        "model": model,
        "task": task,
        "latency_ms": ms,
        "status": status,
        "prompt_version": None,
        "tokens_in": None,
        "tokens_out": None,
        **kw,
    }


def security_flags() -> dict:
    return {
        "pii_masked_count": 0,
        "pii_types": [],
        "injection_detected": False,
        "injection_snippets": [],
        "output_checks_passed": True,
        "invalid_citations_dropped": 0,
        # Conservative defaults also cover legacy rows without provenance metadata.
        **provenance([], "lightweight_hash"),
    }


@dataclass
class TextChunk:
    """Provider text delta, or terminal completion metadata (never a rule fallback)."""

    text: str = ""
    traces: list[dict] = field(default_factory=list)
    finished: bool = False


class ModelUnavailable(Exception):
    """Safe failure marker; do not attach upstream exception text or response bodies."""

    def __init__(self, traces: list[dict] | None = None):
        super().__init__("LLM generation unavailable")
        self.traces = traces or []
