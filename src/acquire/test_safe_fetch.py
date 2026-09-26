import json
import os

import pytest

from src.acquire import safe_fetch

FAKE_URL = "http://cropshift-does-not-exist.invalid/api"


@pytest.fixture(autouse=True)
def temp_dirs(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    fixture_dir = tmp_path / "demo_fixtures"
    monkeypatch.setattr(safe_fetch, "CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(safe_fetch, "FIXTURE_DIR", str(fixture_dir))
    monkeypatch.delenv("OFFLINE", raising=False)
    return cache_dir, fixture_dir


def test_falls_back_to_fixture_when_live_fails_and_no_cache(temp_dirs):
    _, fixture_dir = temp_dirs
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "demo_point.json").write_text(json.dumps({"value": 42}))

    data, mode = safe_fetch.fetch_json(FAKE_URL, {}, "demo_point")

    assert data == {"value": 42}
    assert mode == "fixture"


def test_falls_back_to_cache_when_live_fails_and_fixture_missing(temp_dirs):
    cache_dir, _ = temp_dirs
    cache_dir.mkdir(parents=True)
    (cache_dir / "demo_point.json").write_text(json.dumps({"value": 7}))

    data, mode = safe_fetch.fetch_json(FAKE_URL, {}, "demo_point")

    assert data == {"value": 7}
    assert mode == "cache"


def test_raises_when_live_fails_and_nothing_cached(temp_dirs):
    with pytest.raises(RuntimeError):
        safe_fetch.fetch_json(FAKE_URL, {}, "demo_point")


def test_offline_env_skips_live_and_uses_fixture(temp_dirs, monkeypatch):
    _, fixture_dir = temp_dirs
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "demo_point.json").write_text(json.dumps({"value": 1}))
    monkeypatch.setenv("OFFLINE", "1")

    data, mode = safe_fetch.fetch_json(FAKE_URL, {}, "demo_point")

    assert data == {"value": 1}
    assert mode == "fixture"


def test_stale_cache_with_no_fixture_is_used_as_last_resort(temp_dirs):
    cache_dir, _ = temp_dirs
    cache_dir.mkdir(parents=True)
    cache_path = cache_dir / "demo_point.json"
    cache_path.write_text(json.dumps({"value": "stale"}))
    os.utime(cache_path, (0, 0))  # far older than any ttl

    data, mode = safe_fetch.fetch_json(FAKE_URL, {}, "demo_point", ttl_hours=1)

    assert data == {"value": "stale"}
    assert mode == "cache"
