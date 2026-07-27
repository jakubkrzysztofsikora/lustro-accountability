"""Tests for the append-only snapshot store (mocked API client)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lustro_accountability import snapshots as snap_mod


class FakeClient:
    def __init__(self, corrections=None, feed=None, health=None):
        self._corrections = corrections or []
        self._feed = feed or []
        self._health = health or {}
        self.calls = 0

    def get_corrections(self):
        self.calls += 1
        return self._corrections

    def get_feed(self):
        self.calls += 1
        return self._feed

    def get_health(self):
        self.calls += 1
        return self._health


def test_take_and_write_snapshot(tmp_path):
    client = FakeClient(
        corrections=[{"id": "c1", "state": "open"}],
        feed=[{"id": "a1", "type": "advisory"}],
        health={"classifier": {"classifier_loaded": False}},
    )
    ts = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)
    snap = snap_mod.take_snapshot(client, fetched_at=ts)
    assert snap.fetched_at == "2026-07-27T12:00:00Z"
    assert client.calls == 3

    path = snap_mod.write_snapshot(snap, tmp_path)
    assert path.name == "2026-07-27T120000Z.json"
    loaded = snap_mod.load_snapshots(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].corrections == [{"id": "c1", "state": "open"}]


def test_snapshots_are_append_only(tmp_path):
    ts = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)
    snap = snap_mod.take_snapshot(FakeClient(), fetched_at=ts)
    snap_mod.write_snapshot(snap, tmp_path)
    with pytest.raises(FileExistsError):
        snap_mod.write_snapshot(snap, tmp_path)


def test_load_snapshots_chronological_and_skips_malformed(tmp_path):
    for i, ts in enumerate(
        [
            datetime(2026, 7, 27, 14, 0, 0, tzinfo=UTC),
            datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC),
        ]
    ):
        snap = snap_mod.take_snapshot(FakeClient(corrections=[{"id": f"c{i}"}]), fetched_at=ts)
        snap_mod.write_snapshot(snap, tmp_path)
    (tmp_path / "2026-07-27T130000Z.json").write_text("{not json", encoding="utf-8")
    loaded = snap_mod.load_snapshots(tmp_path)
    assert [s.fetched_at for s in loaded] == [
        "2026-07-27T12:00:00Z",
        "2026-07-27T14:00:00Z",
    ]


def test_load_snapshots_empty_dir(tmp_path):
    assert snap_mod.load_snapshots(tmp_path / "missing") == []
