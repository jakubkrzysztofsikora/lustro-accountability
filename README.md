# lustro-accountability

**Supportive, independent oversight for [LUSTRO](https://projektlustro.eu)'s own transparency promises.**

LUSTRO is a grassroots Polish counter-disinformation (FIMI) project with a fully public,
key-less, cryptographically signed read API. This monitor tracks two of the project's
self-imposed transparency commitments:

1. **The open corrections ledger** (`/v1/corrections`) — correction count over time, state
   transitions, and the latency between an original advisory's `published_at` and the
   correction's `published_at`.
2. **Scoring health** (`/api/health`) — alerts (log + optional webhook) whenever
   `classifier.classifier_loaded` flips, plus a historical uptime/degradation timeline of
   scoring-backend quality.

**Credit where due:** LUSTRO's open-corrections design — signed correction records served
publicly by the API — is what makes independent oversight like this possible at all. This
project exists to *support* that transparency, not to attack the project.

LUSTRO tracks **narratives, not people**. Data is de-identified by design; nothing here
attempts re-identification. Every referenced advisory links back to projektlustro.eu, and no
full text is cached beyond the fields the public API serves.

## How it works

- **Git is the database.** Every run appends one immutable JSON snapshot per run to
  `snapshots/YYYY-MM-DDTHHMMSSZ.json` recording `fetched_at`, the corrections list, the feed
  items (public fields, for the latency join), and the health payload. Snapshots are never
  modified or deleted.
- **Hourly GitHub Action** (staged in `workflows-staging/` — see below) takes a snapshot
  (3 polite requests, spaced ≥10s; 24 runs/day is far under the 30 req/min API limit),
  checks for a classifier health flip, rebuilds the static site, and commits.
- **Static site** (`site/`) — plain HTML/CSS with inline SVG charts. Chosen deliberately:
  zero JS build/runtime dependencies, fully auditable output, trivially hostable on GitHub
  Pages. Polish-first with an English toggle. Deployed via a Pages workflow (also staged).

### Latency join assumption

A correction's `match_id` is treated as the advisory id when it matches a feed item;
otherwise we fall back to joining on the shared `cluster` UUID (the correction then refers
to the earliest-seen advisory in that cluster). Unmatched corrections are shown honestly as
`unmatched`. Only public API fields are used.

## Usage

```bash
pip install -e .
lustro-accountability --min-interval 10 snapshot      # fetch + append snapshot
lustro-accountability build-site                      # rebuild site/ from snapshots
lustro-accountability check-health-flip               # exit 1 if classifier_loaded flipped
```

Optional webhook alerting on classifier flips:

```bash
export ACCOUNTABILITY_WEBHOOK_URL=https://example.org/hook
lustro-accountability check-health-flip
```

## Development

```bash
pip install -e '.[dev]'
pytest          # all API access is mocked; no live requests
ruff check .
```

## Workflows staging note

GitHub Actions workflows live in `workflows-staging/` because the publishing token cannot
write to `.github/workflows/`. To activate, move:

- `workflows-staging/hourly-update.yml` → `.github/workflows/hourly-update.yml`
- `workflows-staging/pages-deploy.yml` → `.github/workflows/pages-deploy.yml`

then enable GitHub Pages (source: GitHub Actions) in repo settings.

## License

MIT
