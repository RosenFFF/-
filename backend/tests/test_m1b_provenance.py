"""UI-visible provenance must survive every fallback and never launder synthetic sources."""

import json
from pathlib import Path

import pytest

from app.services.provenance import COMPLIANCE_DISCLAIMER, corpus_of

from . import test_m1_pipeline as pipeline

_report = pipeline._report
fake_api = pipeline.fake_api
quick_ocr = pipeline.quick_ocr


def assert_labels(payload):
    flags = payload["security"]
    assert flags["rule_corpus"] in {"synthetic", "mixed", "public_verified"}
    assert flags["rule_corpus_label"]
    assert flags["retrieval_mode"] == "lightweight_hash"
    assert flags["compliance_disclaimer"] == COMPLIANCE_DISCLAIMER


async def test_ui_labels_on_recognition_review_create_get_and_list(fake_api, quick_ocr):
    client = await fake_api.login("reviewer")
    doc_id, _, report = await _report(fake_api, client)
    recognition = (await client.get(f"/api/v1/documents/{doc_id}/recognition")).json()
    assert_labels(recognition)
    assert recognition["security"]["rule_corpus"] == "mixed"
    assert_labels(report)
    assert report["security"]["rule_corpus"] == "mixed"
    assert report["summary"].startswith("混合语料（含合成")
    assert COMPLIANCE_DISCLAIMER in report["summary"]
    created = await client.post("/api/v1/reviews", json={"document_ids": [doc_id], "destination_country": "VN"})
    assert created.status_code == 202
    assert_labels(created.json())
    listed = (await client.get("/api/v1/reviews")).json()
    for item in listed["items"]:
        assert_labels(item)
    for finding in report["findings"]:
        for citation in finding["citations"]:
            assert citation["source_kind"] in {"synthetic", "public"}
            assert "source_kind_label" in citation
            assert "article" in citation
            assert "url" in citation
            assert citation.get("excerpt_kind") == "summary"
            assert citation.get("applicability") == "unverified"
            assert "version_date" in citation
            if citation["rule_id"].startswith("SYN-"):
                assert citation["corpus"] == "synthetic"
                assert citation["source_kind"] == "synthetic"
                assert citation["jurisdiction"] == "SYNTHETIC"
                assert "合成" in citation["source"]
                assert finding["determined_by"] in {"rule", "llm"}


async def test_fallback_and_legacy_rows_do_not_omit_labels(api, quick_ocr):
    from app.db.models import DocumentFields, Review

    client = await api.login("reviewer")
    doc_id, review_id, report = await _report(api, client)
    assert report["degrade_level"] == "L3"
    assert report["degrade_status"] == "规则引擎降级，需人工复核"
    assert report["llm_verified"] is False
    assert_labels(report)
    async with api.app.state.db.maintenance_sessionmaker() as session:
        for cls, rid in [(DocumentFields, doc_id), (Review, review_id)]:
            row = await session.get(cls, rid)
            row.security = {}
        await session.commit()
    assert_labels((await client.get(f"/api/v1/documents/{doc_id}/recognition")).json())
    assert_labels((await client.get(f"/api/v1/reviews/{review_id}")).json())


async def test_public_rules_have_traceable_source_and_are_retrieved(api):
    index = api.app.state.ai.rag
    public = [r for r in index.rules.values() if r.get("corpus") == "public_verified"]
    assert len(public) >= 5
    for rule in public:
        assert all(
            rule.get(k) for k in ("id", "source", "jurisdiction", "article", "title", "text", "url", "verified_at")
        )
        assert rule["url"].startswith("https://")
    citations, _ = index.search("商业发票必要项 invoice quantity currency 原产国 美国进口")
    assert any(c["corpus"] == "public_verified" and c["url"].startswith("https://") for c in citations)
    for rule in public:
        citation = index.citation(rule["id"])
        assert corpus_of([citation]) == "public_verified"
        assert corpus_of([citation, index.citation("SYN-HS")]) == "mixed"
    assert corpus_of([]) == "synthetic"


@pytest.mark.parametrize(
    "patch",
    [
        {"rule_id": "SYN-X"},
        {"source": "合成来源"},
        {"jurisdiction": "SYNTHETIC"},
        {"url": None},
        {"url": "file:///tmp/rule"},
        {"verified_at": None},
        {"corpus": "unverified"},
    ],
)
def test_url_or_claim_cannot_promote_unverified_rule(patch):
    rule = {
        "rule_id": "PUB-X",
        "source": "公开来源",
        "jurisdiction": "CN",
        "url": "https://example.invalid/law",
        "verified_at": "2026-11-05",
        "corpus": "public_verified",
    }
    assert corpus_of([{**rule, **patch}]) == "synthetic"


async def test_system_exposes_human_readable_lightweight_modes(api):
    client = await api.login("reviewer")
    result = (await client.get("/api/v1/system/models")).json()
    models = [m for m in result["models"] if m["category"] in {"embedding", "reranker"}]
    assert len(models) == 2
    for item in models:
        assert item["lightweight"] and item["retrieval_mode"] == "lightweight_hash"
        assert item["implementation_mode"].startswith("lightweight_")
        assert "非 BGE" in item["mode_label"]


def test_public_and_synthetic_files_remain_separate():
    path = Path(__file__).parents[1] / "data" / "rules"
    assert all(r["id"].startswith("SYN-") for r in json.loads((path / "synthetic-trade.json").read_text()))
    assert all(not r["id"].startswith("SYN-") for r in json.loads((path / "public-trade.json").read_text()))


def test_degrade_status_is_explicit_not_just_l3():
    from app.services.provenance import DEGRADE_STATUS, degrade_fields

    fields = degrade_fields("L3")
    assert fields["degrade_level"] == "L3"
    assert fields["degrade_status"] == DEGRADE_STATUS["L3"] == "规则引擎降级，需人工复核"
    assert fields["llm_verified"] is False
    assert degrade_fields("L0")["llm_verified"] is True


def test_source_kind_is_stable_frontend_badge_field():
    from app.services.provenance import SOURCE_KIND_LABELS, provenance, source_kind_of_corpus

    assert source_kind_of_corpus("public_verified") == "public"
    assert source_kind_of_corpus("mixed") == "synthetic"
    assert source_kind_of_corpus("synthetic") == "synthetic"
    flags = provenance([], "lightweight_hash")
    assert flags["source_kind"] == "synthetic"
    assert flags["source_kind_label"] == SOURCE_KIND_LABELS["synthetic"] == "合成规则 · 非真实合规结论"


async def test_rule_detail_exposes_unified_provenance(api):
    c = await api.login("reviewer")
    synthetic = (await c.get("/api/v1/rules/SYN-REQUIRED")).json()
    assert synthetic["source_kind"] == "synthetic"
    assert synthetic["source_kind_label"] == "合成规则 · 非真实合规结论"
    assert synthetic["excerpt_kind"] == "summary"
    assert synthetic["applicability"] == "unverified"
    assert "version_date" in synthetic
    public = (await c.get("/api/v1/rules/PUB-CN-ORIGIN")).json()
    assert public["source_kind"] == "public"
    assert public["url"].startswith("https://")
    assert public["version_date"] == public["verified_at"]
    assert public["corpus"] == "public_verified"
    missing = await c.get("/api/v1/rules/NO-SUCH-RULE")
    assert missing.status_code == 404
