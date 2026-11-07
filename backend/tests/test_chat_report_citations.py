"""Fixture-only (FakeLLM): follow-up citation allow-set = retrieval + rules cited by THIS report.

Not real-model evidence; the real DeepSeek multi-question regression is test_deepseek_chat_diagnosis.py.
"""

import json

import pytest

from app.ai.types import TextChunk, trace

from .fakes import FakeLLM
from .test_m1_chat_sse import parse_sse, path, seed_review

QUESTION = "What should I verify next?"


@pytest.fixture
async def chat_api(api):
    api.app.state.ai.llm = FakeLLM()
    return api


def fixed_llm(text):
    class Fixed(FakeLLM):
        async def chat_stream(self, messages, *, task):
            self.messages.append((task, messages))
            yield TextChunk(text=text)
            yield TextChunk(finished=True, traces=[trace("llm", "test-fixture-only", "chat", 1, provider="fake")])

    return Fixed()


def outside_retrieval(app, n=2):
    rag = app.state.ai.rag
    retrieved = {c["rule_id"] for c in rag.search(QUESTION)[0]}
    spare = [rid for rid in rag.rules if rid not in retrieved]
    assert len(spare) >= n
    return spare[:n]


def finding(app, rid, score=0.42):
    return {"title": "fixture", "severity": "medium", "citations": [app.state.ai.rag.citation(rid, score)]}


async def ask(chat_api, rid):
    c = await chat_api.login("reviewer")
    try:
        r = await c.post(path(rid), json={"content": QUESTION}, headers={"Accept": "text/event-stream"})
        return parse_sse(r)
    finally:
        await c.aclose()


async def test_broad_followup_may_cite_rule_from_own_report_outside_retrieval(chat_api):
    report_rule, _ = outside_retrieval(chat_api.app)
    rid = await seed_review(chat_api, findings=[finding(chat_api.app, report_rule)])
    llm = fixed_llm(f"Re-check the item flagged in the report [{report_rule}].")
    chat_api.app.state.ai.llm = llm
    events = await ask(chat_api, rid)
    names = [e["event"] for e in events]
    assert names == ["delta", "citation", "done"]
    cite = events[1]["data"]
    # Rebuilt from the corpus, not copied from stored finding text.
    assert cite == chat_api.app.state.ai.rag.citation(report_rule, 0.42)
    sent = json.loads(llm.messages[0][1][1]["content"])
    assert report_rule in {c["rule_id"] for c in sent["allowed_rules"]}


async def test_rule_neither_retrieved_nor_in_report_is_still_rejected(chat_api):
    report_rule, stranger = outside_retrieval(chat_api.app)
    rid = await seed_review(chat_api, findings=[finding(chat_api.app, report_rule)])
    chat_api.app.state.ai.llm = fixed_llm(f"Unrelated rule [{stranger}].")
    events = await ask(chat_api, rid)
    assert [e["event"] for e in events] == ["error"]
    assert events[0]["data"]["code"] == "MODEL_UNAVAILABLE"


async def test_non_corpus_id_stored_in_findings_is_never_admitted(chat_api):
    forged = {"title": "fixture", "citations": [{"rule_id": "FORGED-1", "score": 1, "excerpt": "x"}]}
    rid = await seed_review(chat_api, findings=[forged])
    llm = fixed_llm("See [FORGED-1].")
    chat_api.app.state.ai.llm = llm
    events = await ask(chat_api, rid)
    assert [e["event"] for e in events] == ["error"]
    sent = json.loads(llm.messages[0][1][1]["content"])
    assert "FORGED-1" not in {c["rule_id"] for c in sent["allowed_rules"]}


@pytest.mark.parametrize("extra", [0, 1])
async def test_allowed_set_is_bounded(chat_api, extra):
    retrieved = len(chat_api.app.state.ai.rag.search(QUESTION)[0])
    chat_api.settings.chat_max_allowed_rules = retrieved + extra
    spare = outside_retrieval(chat_api.app, n=2)
    rid = await seed_review(chat_api, findings=[finding(chat_api.app, r) for r in spare])
    llm = fixed_llm("Short answer without citations.")
    chat_api.app.state.ai.llm = llm
    assert [e["event"] for e in await ask(chat_api, rid)] == ["delta", "done"]
    sent = json.loads(llm.messages[0][1][1]["content"])
    assert len(sent["allowed_rules"]) == retrieved + extra
