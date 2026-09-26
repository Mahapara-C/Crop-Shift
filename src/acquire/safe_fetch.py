"""
src/acquire/safe_fetch.py

Online-first fetch helper: try a live HTTP GET, fall back to a per-point
per-day cache, then to a checked-in demo fixture. Never raises during a
demo if either a cache entry or a fixture exists for cache_key.

Layout:
    cache/<cache_key>.json         -- gitignored, written after a live hit
    demo_fixtures/<cache_key>.json -- checked in, hand-picked demo data

Set OFFLINE=1 to skip the live request entirely and go straight to
cache/fixture (useful on stage with no network, or in tests).
"""

import json
import os
import time

import requests

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CACHE_DIR = os.path.join(REPO_ROOT, "cache")
FIXTURE_DIR = os.path.join(REPO_ROOT, "demo_fixtures")


def _cache_path(cache_key):
    return os.path.join(CACHE_DIR, f"{cache_key}.json")


def _fixture_path(cache_key):
    return os.path.join(FIXTURE_DIR, f"{cache_key}.json")


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _cache_is_fresh(path, ttl_hours):
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours <= ttl_hours


def _write_cache(cache_key, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(cache_key), "w", encoding="utf-8") as f:
        json.dump(data, f)


def fetch_json(url, params, cache_key, ttl_hours=24):
    """Fetch JSON from `url`, live first, then cache, then fixture.

    Returns (data, source_mode) where source_mode is "live", "cache", or
    "fixture". Raises only if none of the three is available.
    """
    offline = os.environ.get("OFFLINE") == "1"
    cache_path = _cache_path(cache_key)
    fixture_path = _fixture_path(cache_key)

    if not offline:
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            _write_cache(cache_key, data)
            return data, "live"
        except Exception:
            pass

    if os.path.exists(cache_path) and _cache_is_fresh(cache_path, ttl_hours):
        return _read_json(cache_path), "cache"

    if os.path.exists(fixture_path):
        return _read_json(fixture_path), "fixture"

    if os.path.exists(cache_path):
        return _read_json(cache_path), "cache"

    raise RuntimeError(
        f"fetch_json: live fetch failed for {cache_key!r} and no cache or "
        f"fixture is available at {cache_path!r} / {fixture_path!r}"
    )
