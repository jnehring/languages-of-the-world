from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from low.scraper.cache import FileCache
from low.scraper.fetch import serper_search
from low.scraper.llm import GeminiClient
from low.scraper.pipeline import PipelineConfig, run_pipeline
from low.scraper.state import (
    RESPONSE_COLUMN,
    load_pipeline_state,
    round_results_path,
)
from low.scraper.tasks import get_task
from low.scraper.tasks.speakers import SpeakerCountTask, parse_speaker_count


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("42000", 42000),
        ("42,000", 42000),
        ("UNKNOWN", None),
        ("", None),
        ("no number here", None),
        ("-5", None),
    ],
)
def test_parse_speaker_count(raw, expected):
    assert parse_speaker_count(raw) == expected


def test_speaker_task_merge_values():
    task = SpeakerCountTask()
    assert task.merge_values(100, 200) == 200
    assert task.merge_values(None, 50) == 50


def test_serper_cache_hit(tmp_path):
    cache = FileCache(tmp_path)
    calls = []

    def fake_serper(api_key, query):
        calls.append(query)
        return {"organic": [{"link": "https://example.com"}]}

    with patch("low.scraper.fetch._serper_call_with_retry", side_effect=fake_serper):
        r1 = serper_search(cache, "key", "test query", use_cache=True)
        r2 = serper_search(cache, "key", "test query", use_cache=True)

    assert r1 == r2
    assert calls == ["test query"]


def test_serper_no_cache(tmp_path):
    cache = FileCache(tmp_path)
    calls = []

    def fake_serper(api_key, query):
        calls.append(query)
        return {"organic": []}

    with patch("low.scraper.fetch._serper_call_with_retry", side_effect=fake_serper):
        serper_search(cache, "key", "q", use_cache=False)
        serper_search(cache, "key", "q", use_cache=False)

    assert len(calls) == 2


def test_llm_cache_hit(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    cache = FileCache(tmp_path)
    calls = []

    def fake_gemini(api_key, model, prompt):
        calls.append(prompt)
        return "12345"

    with patch("low.scraper.llm._call_gemini_with_retry", side_effect=fake_gemini):
        client = GeminiClient(cache, model="gemini-3.5-flash", use_cache=True)
        assert client.generate("hello") == "12345"
        assert client.generate("hello") == "12345"

    assert calls == ["hello"]


def test_load_pipeline_state_from_round_csv(tmp_path):
    task = SpeakerCountTask()
    path = round_results_path(tmp_path, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["country", "language", "url", "prompt", RESPONSE_COLUMN],
        )
        writer.writeheader()
        writer.writerow(
            {
                "country": "Uganda",
                "language": "Kinyarwanda",
                "url": "https://example.com/a",
                "prompt": "p",
                RESPONSE_COLUMN: "1000",
            }
        )
        writer.writerow(
            {
                "country": "Uganda",
                "language": "Luganda",
                "url": "https://example.com/b",
                "prompt": "p",
                RESPONSE_COLUMN: "UNKNOWN",
            }
        )

    state = load_pipeline_state(tmp_path, task)
    assert ("Uganda", "Kinyarwanda") in state.solved_keys
    assert ("Uganda", "Luganda") not in state.solved_keys
    assert state.best[("Uganda", "Kinyarwanda")][0] == 1000


def test_run_pipeline_mocked(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    task = SpeakerCountTask()

    items = [
        task.item_for_key(
            ("Testland", "Testish"),
            {"country": "Testland", "language": "Testish"},
        )
    ]

    with patch.object(task, "discover_items", return_value=items), patch(
        "low.scraper.pipeline.serper_search",
        return_value={"organic": [{"link": "https://example.com/page"}]},
    ), patch(
        "low.scraper.pipeline.fetch_url", return_value="<html>ok</html>"
    ), patch(
        "low.scraper.pipeline.html_to_markdown", return_value="# Title\n100 speakers"
    ), patch.object(
        GeminiClient, "generate", return_value="5000"
    ):
        config = PipelineConfig(
            data_dir=tmp_path,
            cache_dir=tmp_path / ".cache",
            task=task,
            rounds=1,
            results_per_pair=1,
            workers=1,
            respect_robots=False,
        )
        output = run_pipeline(config)

    assert output.name == "speakers.json"
    records = json.loads(output.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["number_of_speakers"] == 5000
    assert (tmp_path / "round1_results.csv").exists()


def test_run_pipeline_second_round_skips_solved(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    task = SpeakerCountTask()
    item = task.item_for_key(
        ("Testland", "Testish"),
        {"country": "Testland", "language": "Testish"},
    )

    serper_calls = []

    def fake_serper(*args, **kwargs):
        serper_calls.append(1)
        return {"organic": [{"link": "https://example.com/new"}]}

    with patch.object(task, "discover_items", return_value=[item]), patch(
        "low.scraper.pipeline.serper_search", side_effect=fake_serper
    ), patch("low.scraper.pipeline.fetch_url", return_value="<html/>"), patch(
        "low.scraper.pipeline.html_to_markdown", return_value="md"
    ), patch.object(
        GeminiClient, "generate", return_value="100"
    ):
        config = PipelineConfig(
            data_dir=tmp_path,
            cache_dir=tmp_path / ".cache",
            task=task,
            rounds=2,
            workers=1,
            respect_robots=False,
        )
        run_pipeline(config)

    assert len(serper_calls) == 1


def test_get_task_unknown():
    with pytest.raises(SystemExit):
        get_task("nonexistent")
