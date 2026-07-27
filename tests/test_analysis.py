"""Tests for analysis: latency join, state tallies, health-flip detection."""

from __future__ import annotations

import pytest

from lustro_accountability.analysis import analyze, detect_flip, join_latencies
from lustro_accountability.snapshots import Snapshot

ADV = {
    "id": "adv-1",
    "type": "advisory",
    "cluster": "clus-1",
    "published_at": "2026-07-20T10:00:00Z",
}


def _health(loaded: bool) -> dict:
    return {"classifier": {"classifier_loaded": loaded, "scoring_backend": "calibrated_scorer"}}


def test_latency_join_via_match_id():
    snap = Snapshot(
        fetched_at="2026-07-27T00:00:00Z",
        corrections=[
            {
                "id": "corr-1",
                "match_id": "adv-1",
                "cluster": "clus-1",
                "state": "applied",
                "published_at": "2026-07-21T10:00:00Z",
            }
        ],
        feed_items=[ADV],
        health={},
    )
    lats = join_latencies(snap)
    assert len(lats) == 1
    assert lats[0].join_method == "match_id"
    assert lats[0].latency_hours == pytest.approx(24.0)
    assert lats[0].advisory_id == "adv-1"


def test_latency_join_fallback_to_cluster():
    snap = Snapshot(
        fetched_at="2026-07-27T00:00:00Z",
        corrections=[
            {
                "id": "corr-2",
                "match_id": "unknown-id",
                "cluster": "clus-1",
                "state": "applied",
                "published_at": "2026-07-20T16:00:00Z",
            }
        ],
        feed_items=[ADV],
        health={},
    )
    lats = join_latencies(snap)
    assert lats[0].join_method == "cluster"
    assert lats[0].latency_hours == pytest.approx(6.0)


def test_latency_unmatched_and_missing_timestamps():
    snap = Snapshot(
        fetched_at="2026-07-27T00:00:00Z",
        corrections=[{"id": "corr-3", "state": "open"}],
        feed_items=[],
        health={},
    )
    lats = join_latencies(snap)
    assert lats[0].join_method == "unmatched"
    assert lats[0].latency_hours is None


def test_analyze_states_and_timeline():
    snaps = [
        Snapshot(
            fetched_at=f"2026-07-27T0{h}:00:00Z",
            corrections=[{"id": "c1", "state": "open"}, {"id": "c2", "state": "applied"}]
            if h == 2
            else [],
            feed_items=[],
            health=_health(h != 1),
        )
        for h in (0, 1, 2)
    ]
    report = analyze(snaps)
    assert report.snapshot_count == 3
    assert report.correction_count_latest == 2
    assert report.correction_states == {"open": 1, "applied": 1}
    flips = [e.flipped for e in report.health_timeline]
    assert flips == [False, True, True]  # true->false at h1, false->true at h2
    assert report.corrections_over_time[-1]["correction_count"] == 2


def test_detect_flip(monkeypatch, caplog):
    healthy = Snapshot(fetched_at="t1", health=_health(True))
    degraded = Snapshot(fetched_at="t2", health=_health(False))

    flipped, msg = detect_flip([healthy])
    assert not flipped

    flipped, msg = detect_flip([healthy, healthy])
    assert not flipped

    monkeypatch.delenv("ACCOUNTABILITY_WEBHOOK_URL", raising=False)
    with caplog.at_level("WARNING"):
        flipped, msg = detect_flip([healthy, degraded])
    assert flipped
    assert "True -> False" in msg
    assert "HEALTH FLIP" in caplog.text


def test_detect_flip_webhook_called(monkeypatch):
    calls = []
    monkeypatch.setenv("ACCOUNTABILITY_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(
        "lustro_accountability.analysis._post_webhook",
        lambda url, message: calls.append((url, message)),
    )
    flipped, _ = detect_flip(
        [
            Snapshot(fetched_at="t1", health=_health(False)),
            Snapshot(fetched_at="t2", health=_health(True)),
        ]
    )
    assert flipped
    assert len(calls) == 1
    assert calls[0][0] == "https://example.invalid/hook"
