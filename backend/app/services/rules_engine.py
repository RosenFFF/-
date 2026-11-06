"""Deterministic synthetic checks. No real sanctions/legal coverage is claimed."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.db.models import uid

REQUIRED = {
    "commercial_invoice": ["invoice_no", "total_amount", "currency", "hs_code", "origin_country"],
    "packing_list": ["quantity", "packages"],
    "certificate_of_origin": ["certificate_no", "origin_country", "consignee"],
    "customs_declaration": ["declaration_no", "hs_code", "total_amount"],
    "bill_of_lading": ["bill_no", "consignee"],
    "unknown": [],
}


def check(documents: list[dict], rag) -> list[dict]:
    findings = []

    def add(doc, severity, category, title, message, keys, rule):
        blocks = [bid for f in doc.get("fields", []) if f["key"] in keys for bid in f.get("source_block_ids", [])]
        findings.append(
            {
                "id": uid(),
                "severity": severity,
                "category": category,
                "title": title,
                "message": message,
                "document_id": doc.get("id"),
                "field_keys": keys,
                "evidence_block_ids": sorted(set(blocks)),
                "suggestion": "请人工核对原件与适用的官方规范",
                "determined_by": "rule",
                "citations": [rag.citation(rule)],
            }
        )

    for doc in documents:
        fields = {f["key"]: f["value"] for f in doc["fields"]}
        missing = [key for key in REQUIRED[doc["doc_type"]] if not fields.get(key)]
        if missing:
            add(
                doc,
                "medium",
                "missing_field",
                "必填字段缺失",
                "缺失字段：" + ", ".join(missing),
                missing,
                "SYN-REQUIRED",
            )
        hs = fields.get("hs_code")
        if hs and not re.fullmatch(r"(?:\d{6}|\d{8}|\d{10})", hs):
            add(
                doc,
                "medium",
                "classification",
                "HS编码格式异常",
                "示例格式只接受6、8或10位数字；实际归类仍须人工核实",
                ["hs_code"],
                "SYN-HS",
            )
        if all(fields.get(k) for k in ("total_amount", "quantity", "unit_price")):
            try:
                total, qty, price = [
                    Decimal(fields[k].replace(",", "")) for k in ("total_amount", "quantity", "unit_price")
                ]
                if not all(n.is_finite() and n >= 0 for n in (total, qty, price)):
                    raise InvalidOperation
                mismatch = abs(total - qty * price) > Decimal("0.01")
            except (InvalidOperation, ValueError, OverflowError):
                add(
                    doc,
                    "medium",
                    "format",
                    "金额或数量不可解析",
                    "数值必须是有限非负数",
                    ["total_amount", "quantity", "unit_price"],
                    "SYN-AMOUNT",
                )
            else:
                if mismatch:
                    add(
                        doc,
                        "high",
                        "valuation",
                        "金额不一致",
                        "总金额与数量×单价不一致（不含税费、运费与折扣调整）",
                        ["total_amount", "quantity", "unit_price"],
                        "SYN-AMOUNT",
                    )
        goods = fields.get("goods_description") or ""
        if any(term in goods.upper() for term in ("DEMO-RESTRICTED", "SYNTHETIC-EMBARGO")):
            add(
                doc,
                "high",
                "restricted_goods",
                "命中合成禁限标记",
                "仅命中合成测试清单，不代表真实制裁或禁运判断",
                ["goods_description"],
                "SYN-RESTRICTED",
            )
    origins = {f["value"] for d in documents for f in d["fields"] if f["key"] == "origin_country" and f["value"]}
    if len(origins) > 1:
        add(
            documents[0],
            "medium",
            "inconsistency",
            "跨单证原产国不一致",
            "同票单证的原产国字段不一致",
            ["origin_country"],
            "SYN-ORIGIN",
        )
    add(
        {},
        "info",
        "other",
        "合成规则库适用范围",
        "当前规则库是合成测试语料，不构成真实法律依据，报告不能替代人工审查",
        [],
        "SYN-REVIEW",
    )
    return findings


def risk_level(findings: list[dict]) -> str:
    for level in ("high", "medium", "low"):
        if any(f["severity"] == level for f in findings):
            return level
    return "pass"
