"""Tests for the site builder and CLI (offline)."""

from __future__ import annotations

from lustro_accountability.analysis import analyze
from lustro_accountability.cli import main
from lustro_accountability.site import build_site
from lustro_accountability.snapshots import Snapshot, write_snapshot


def _snap(fetched_at="2026-07-27T12:00:00Z", loaded=False, corrections=None):
    return Snapshot(
        fetched_at=fetched_at,
        corrections=corrections if corrections is not None else [],
        feed_items=[
            {
                "id": "adv-1",
                "type": "advisory",
                "cluster": "clus-1",
                "published_at": "2026-07-20T10:00:00Z",
            }
        ],
        health={
            "classifier": {"classifier_loaded": loaded, "scoring_backend": "calibrated_scorer"}
        },
    )


def test_build_site_renders(tmp_path):
    snaps = [_snap()]
    report = analyze(snaps)
    index = build_site(report, snaps[-1].corrections, snaps[-1].fetched_at, tmp_path)
    html = index.read_text(encoding="utf-8")
    assert "LUSTRO Accountability" in html
    assert "projektlustro.eu" in html
    assert "keyword-fallback" in html  # classifier degraded banner (PL + EN text)
    assert "narracje, nie osoby" in html  # narratives, not people framing
    assert "<svg" in html  # inline SVG charts


def test_build_site_with_correction_links_back(tmp_path):
    corr = {
        "id": "corr-1",
        "match_id": "adv-1",
        "cluster": "clus-1",
        "state": "applied",
        "published_at": "2026-07-21T10:00:00Z",
    }
    snaps = [_snap(corrections=[corr])]
    report = analyze(snaps)
    index = build_site(report, corr and [corr], snaps[-1].fetched_at, tmp_path)
    html = index.read_text(encoding="utf-8")
    assert "https://projektlustro.eu/advisory/adv-1" in html
    assert "https://projektlustro.eu/v1/corrections/corr-1" in html
    assert "24.0" in html  # latency hours


def test_cli_build_site_and_check_health_flip(tmp_path, capsys):
    snap_dir = tmp_path / "snapshots"
    out_dir = tmp_path / "site"
    write_snapshot(_snap("2026-07-27T12:00:00Z", loaded=True), snap_dir)
    write_snapshot(_snap("2026-07-27T13:00:00Z", loaded=False), snap_dir)

    assert main(["--snapshots", str(snap_dir), "build-site", "--out", str(out_dir)]) == 0
    assert (out_dir / "index.html").exists()

    assert main(["--snapshots", str(snap_dir), "check-health-flip"]) == 1
    assert "True -> False" in capsys.readouterr().out
