"""Append-only JSON snapshot store — git is the database.

Each snapshot is one file ``snapshots/YYYY-MM-DDTHHMMSSZ.json`` recording the
fetched-at timestamp, the corrections list, the feed items (public API fields
only, for the latency join), and the health payload. Snapshots are never
modified or deleted by this tool.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SNAPSHOT_DIR = Path("snapshots")


def utcnow() -> datetime:
    return datetime.now(UTC)


def snapshot_name(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H%M%SZ") + ".json"


def parse_snapshot_name(name: str) -> datetime | None:
    try:
        return datetime.strptime(name, "%Y-%m-%dT%H%M%SZ.json").replace(tzinfo=UTC)
    except ValueError:
        return None


@dataclass
class Snapshot:
    fetched_at: str
    corrections: list[dict[str, Any]] = field(default_factory=list)
    feed_items: list[dict[str, Any]] = field(default_factory=list)
    health: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched_at": self.fetched_at,
            "corrections": self.corrections,
            "feed_items": self.feed_items,
            "health": self.health,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        if not isinstance(data, dict):
            raise ValueError("snapshot payload is not an object")
        return cls(
            fetched_at=str(data.get("fetched_at", "")),
            corrections=[c for c in data.get("corrections") or [] if isinstance(c, dict)],
            feed_items=[i for i in data.get("feed_items") or [] if isinstance(i, dict)],
            health=data.get("health") if isinstance(data.get("health"), dict) else {},
        )


def take_snapshot(client: Any, fetched_at: datetime | None = None) -> Snapshot:
    """Fetch corrections + feed + health and return a Snapshot.

    ``client`` is anything with get_corrections()/get_feed()/get_health()
    (LustroClient or a test double).
    """
    ts = fetched_at or utcnow()
    corrections = client.get_corrections()
    feed_items = client.get_feed()
    health = client.get_health()
    return Snapshot(
        fetched_at=ts.isoformat().replace("+00:00", "Z"),
        corrections=corrections,
        feed_items=feed_items,
        health=health,
    )


def write_snapshot(snap: Snapshot, directory: Path | str = SNAPSHOT_DIR) -> Path:
    """Write a snapshot; refuses to overwrite an existing file (append-only)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        ts = datetime.fromisoformat(snap.fetched_at.replace("Z", "+00:00"))
    except ValueError:
        ts = utcnow()
    path = directory / snapshot_name(ts)
    if path.exists():
        raise FileExistsError(f"snapshot {path} already exists — snapshots are append-only")
    path.write_text(json.dumps(snap.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log.info("wrote snapshot %s", path)
    return path


def load_snapshots(directory: Path | str = SNAPSHOT_DIR) -> list[Snapshot]:
    """Load all snapshots in chronological order, skipping malformed files."""
    directory = Path(directory)
    out: list[tuple[datetime, Snapshot]] = []
    if not directory.is_dir():
        return []
    for path in sorted(directory.glob("*.json")):
        ts = parse_snapshot_name(path.name)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            snap = Snapshot.from_dict(data)
        except (ValueError, OSError) as exc:
            log.warning("skipping malformed snapshot %s: %s", path, exc)
            continue
        if ts is None:
            try:
                ts = datetime.fromisoformat(snap.fetched_at.replace("Z", "+00:00"))
            except ValueError:
                continue
        out.append((ts, snap))
    out.sort(key=lambda pair: pair[0])
    return [snap for _, snap in out]
