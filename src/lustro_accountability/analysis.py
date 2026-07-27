"""Analysis over the append-only snapshot history.

- Correction counts over time and per-state tallies.
- Latency between an original advisory's published_at and the correction's
  published_at. JOIN ASSUMPTION: a correction's ``match_id`` is the advisory id
  when present; otherwise we fall back to joining on the shared ``cluster``
  UUID (the correction then refers to the earliest-seen advisory in that
  cluster). Both joins only use public API fields.
- classifier_loaded flip detection across consecutive snapshots.
"""

from __future__ import annotations

import logging
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .snapshots import Snapshot

log = logging.getLogger(__name__)

WEBHOOK_ENV = "ACCOUNTABILITY_WEBHOOK_URL"


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def classifier_loaded(health: dict[str, Any]) -> bool | None:
    clf = health.get("classifier")
    if not isinstance(clf, dict):
        return None
    val = clf.get("classifier_loaded")
    return val if isinstance(val, bool) else None


def scoring_backend(health: dict[str, Any]) -> str:
    clf = health.get("classifier")
    if isinstance(clf, dict) and isinstance(clf.get("scoring_backend"), str):
        return clf["scoring_backend"]
    return "unknown"


@dataclass
class CorrectionLatency:
    correction_id: str
    advisory_id: str | None
    join_method: str  # "match_id" | "cluster" | "unmatched"
    correction_published_at: str | None
    advisory_published_at: str | None
    latency_hours: float | None


@dataclass
class HealthEvent:
    fetched_at: str
    classifier_loaded: bool | None
    scoring_backend: str
    flipped: bool


@dataclass
class AnalysisReport:
    snapshot_count: int
    correction_count_latest: int
    correction_states: dict[str, int]
    latencies: list[CorrectionLatency] = field(default_factory=list)
    latency_stats: dict[str, float | int | None] = field(default_factory=dict)
    health_timeline: list[HealthEvent] = field(default_factory=list)
    corrections_over_time: list[dict[str, Any]] = field(default_factory=list)


def join_latencies(snap: Snapshot) -> list[CorrectionLatency]:
    """Join corrections to advisories within a single snapshot."""
    advisories = [i for i in snap.feed_items if i.get("type", "advisory") == "advisory"]
    by_id = {a.get("id"): a for a in advisories if a.get("id")}
    by_cluster: dict[str, list[dict[str, Any]]] = {}
    for a in advisories:
        cluster = a.get("cluster")
        if isinstance(cluster, str):
            by_cluster.setdefault(cluster, []).append(a)
    for items in by_cluster.values():
        # ISO-8601 timestamps sort chronologically as strings.
        items.sort(key=lambda a: a.get("published_at") or "")

    out: list[CorrectionLatency] = []
    for corr in snap.corrections:
        corr_id = str(corr.get("id", ""))
        corr_ts_raw = corr.get("published_at")
        corr_ts = _parse_ts(corr_ts_raw)
        advisory: dict[str, Any] | None = None
        method = "unmatched"
        match_id = corr.get("match_id")
        if isinstance(match_id, str) and match_id in by_id:
            advisory = by_id[match_id]
            method = "match_id"
        else:
            cluster = corr.get("cluster")
            if isinstance(cluster, str) and by_cluster.get(cluster):
                advisory = by_cluster[cluster][0]
                method = "cluster"
        latency_hours: float | None = None
        adv_ts_raw = advisory.get("published_at") if advisory else None
        adv_ts = _parse_ts(adv_ts_raw)
        if corr_ts is not None and adv_ts is not None:
            latency_hours = round((corr_ts - adv_ts).total_seconds() / 3600.0, 3)
        out.append(
            CorrectionLatency(
                correction_id=corr_id,
                advisory_id=advisory.get("id") if advisory else None,
                join_method=method,
                correction_published_at=corr_ts_raw if isinstance(corr_ts_raw, str) else None,
                advisory_published_at=adv_ts_raw if isinstance(adv_ts_raw, str) else None,
                latency_hours=latency_hours,
            )
        )
    return out


def _latency_stats(latencies: list[CorrectionLatency]) -> dict[str, float | int | None]:
    vals = sorted(lt.latency_hours for lt in latencies if lt.latency_hours is not None)
    if not vals:
        return {"count": 0, "min_hours": None, "median_hours": None, "max_hours": None}
    mid = len(vals) // 2
    median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    return {
        "count": len(vals),
        "min_hours": round(vals[0], 3),
        "median_hours": round(median, 3),
        "max_hours": round(vals[-1], 3),
    }


def analyze(snapshots: list[Snapshot]) -> AnalysisReport:
    report = AnalysisReport(
        snapshot_count=len(snapshots),
        correction_count_latest=len(snapshots[-1].corrections) if snapshots else 0,
        correction_states={},
    )
    if snapshots:
        latest = snapshots[-1]
        for corr in latest.corrections:
            state = str(corr.get("state", "unknown"))
            report.correction_states[state] = report.correction_states.get(state, 0) + 1
        report.latencies = join_latencies(latest)
        report.latency_stats = _latency_stats(report.latencies)

    prev: bool | None = None
    first = True
    for snap in snapshots:
        loaded = classifier_loaded(snap.health)
        flipped = False
        if first:
            flipped = False
            first = False
        elif loaded is not None and prev is not None and loaded != prev:
            flipped = True
        if loaded is not None:
            prev = loaded
        report.health_timeline.append(
            HealthEvent(
                fetched_at=snap.fetched_at,
                classifier_loaded=loaded,
                scoring_backend=scoring_backend(snap.health),
                flipped=flipped,
            )
        )
        report.corrections_over_time.append(
            {"fetched_at": snap.fetched_at, "correction_count": len(snap.corrections)}
        )
    return report


def detect_flip(snapshots: list[Snapshot]) -> tuple[bool, str]:
    """Check whether classifier_loaded flipped between the last two snapshots.

    Returns (flipped, message). Alerts via log and optional webhook.
    """
    if len(snapshots) < 2:
        return False, "fewer than two snapshots; nothing to compare"
    prev, cur = snapshots[-2], snapshots[-1]
    prev_loaded = classifier_loaded(prev.health)
    cur_loaded = classifier_loaded(cur.health)
    if prev_loaded is None or cur_loaded is None or prev_loaded == cur_loaded:
        return False, f"no flip (previous={prev_loaded}, current={cur_loaded})"
    message = (
        "LUSTRO classifier_loaded changed "
        f"{prev_loaded} -> {cur_loaded} at {cur.fetched_at} "
        f"(backend: {scoring_backend(cur.health)})"
    )
    log.warning("HEALTH FLIP: %s", message)
    webhook = os.environ.get(WEBHOOK_ENV)
    if webhook:
        _post_webhook(webhook, message)
    return True, message


def _post_webhook(url: str, message: str) -> None:
    payload = ('{"text": ' + _json_str(message) + "}").encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info("webhook delivered (HTTP %s)", resp.status)
    except OSError as exc:
        log.error("webhook delivery failed: %s", exc)


def _json_str(value: str) -> str:
    import json

    return json.dumps(value)
