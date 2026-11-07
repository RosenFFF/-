"""One separately authorized five-sample review run. No chat or automatic reruns."""

import os

import pytest

from .test_model_fp_capture import capture_no_chat

PROMPT_SAMPLE_IDS = (1, 9, 12, 15, 18)  # clean, missing, HS, amount, restricted


@pytest.mark.skipif(os.environ.get("RUN_PROMPT_FIVE_E2E") != "1", reason="explicit five-sample paid validation only")
async def test_prompt_five_once(tmp_path, postgres_rls_db, live_redis, monkeypatch):
    await capture_no_chat(tmp_path, postgres_rls_db, live_redis, monkeypatch, sample_ids=PROMPT_SAMPLE_IDS)
