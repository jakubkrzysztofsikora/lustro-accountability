"""CLI: lustro-accountability snapshot | build-site | check-health-flip."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import snapshots as snap_mod
from .analysis import analyze, detect_flip
from .client import LustroClient
from .site import build_site


def cmd_snapshot(args: argparse.Namespace) -> int:
    with LustroClient(base_url=args.base_url, min_interval=args.min_interval) as client:
        snap = snap_mod.take_snapshot(client)
    path = snap_mod.write_snapshot(snap, args.snapshots)
    print(f"snapshot written: {path}")
    print(
        f"  corrections: {len(snap.corrections)}, feed items: {len(snap.feed_items)}, "
        f"classifier_loaded: {snap.health.get('classifier', {}).get('classifier_loaded')}"
    )
    return 0


def cmd_build_site(args: argparse.Namespace) -> int:
    snapshots = snap_mod.load_snapshots(args.snapshots)
    report = analyze(snapshots)
    corrections = snapshots[-1].corrections if snapshots else []
    generated_at = snapshots[-1].fetched_at if snapshots else "n/a"
    index = build_site(report, corrections, generated_at, args.out)
    print(f"site built: {index} (from {len(snapshots)} snapshot(s))")
    return 0


def cmd_check_health_flip(args: argparse.Namespace) -> int:
    snapshots = snap_mod.load_snapshots(args.snapshots)
    flipped, message = detect_flip(snapshots)
    print(message)
    return 1 if flipped else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lustro-accountability",
        description="Supportive independent oversight for LUSTRO's corrections & health.",
    )
    parser.add_argument("--base-url", default="https://projektlustro.eu")
    parser.add_argument(
        "--snapshots", type=Path, default=Path("snapshots"), help="snapshot directory"
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=0.0,
        help="minimum seconds between live API requests (politeness)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="fetch corrections+feed+health and append a snapshot")
    bs = sub.add_parser("build-site", help="rebuild the static site from snapshots")
    bs.add_argument("--out", type=Path, default=Path("site"))
    sub.add_parser(
        "check-health-flip",
        help="exit 1 if classifier_loaded flipped between the last two snapshots",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    handlers = {
        "snapshot": cmd_snapshot,
        "build-site": cmd_build_site,
        "check-health-flip": cmd_check_health_flip,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
