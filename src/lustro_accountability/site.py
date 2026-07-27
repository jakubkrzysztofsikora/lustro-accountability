"""Static site builder for the accountability page.

Choice of stack: hand-rendered plain HTML/CSS with inline SVG charts.
Justification: zero build/runtime JS dependencies, fully auditable output,
trivially hostable on GitHub Pages, and accessible by default. Polish-first
with English fallback (hard rule 7) via a small client-side toggle.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .analysis import AnalysisReport, HealthEvent

SITE_DIR = Path("site")
ADVISORY_URL = "https://projektlustro.eu/advisory/{id}"
CORRECTION_URL = "https://projektlustro.eu/v1/corrections/{id}"


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _t(pl: str, en: str) -> str:
    return f'<span lang="pl">{_esc(pl)}</span><span lang="en" hidden>{_esc(en)}</span>'


def _svg_health_timeline(events: list[HealthEvent], width: int = 720, height: int = 90) -> str:
    if not events:
        return "<p><em>No health data yet.</em></p>"
    n = len(events)
    step = width / max(n, 1)
    bars: list[str] = []
    for i, ev in enumerate(events):
        if ev.classifier_loaded is True:
            color, label = "#2e7d32", "classifier loaded"
        elif ev.classifier_loaded is False:
            color, label = "#c62828", "keyword-fallback scoring (classifier not loaded)"
        else:
            color, label = "#9e9e9e", "unknown"
        x = i * step
        stroke = ' stroke="#ffca28" stroke-width="3"' if ev.flipped else ""
        bars.append(
            f'<rect x="{x:.1f}" y="10" width="{max(step - 2, 1):.1f}" height="{height - 20}" '
            f'fill="{color}"{stroke} rx="2"><title>{_esc(ev.fetched_at)} — {label}'
            f"{' — FLIP' if ev.flipped else ''} "
            f"(backend: {_esc(ev.scoring_backend)})</title></rect>"
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Classifier health timeline" style="width:100%;max-width:720px;height:auto">'
        + "".join(bars)
        + "</svg>"
        + '<p class="legend"><span class="sw ok"></span> classifier loaded '
        '<span class="sw bad"></span> keyword-fallback scoring '
        '<span class="sw unk"></span> unknown '
        '<span class="sw flip"></span> state flip</p>'
    )


def _svg_corrections_over_time(
    points: list[dict[str, Any]], width: int = 720, height: int = 160
) -> str:
    if not points:
        return "<p><em>No snapshots yet.</em></p>"
    counts = [int(p.get("correction_count", 0)) for p in points]
    max_c = max(counts) or 1
    n = len(points)
    step = width / max(n - 1, 1)
    coords = [(i * step, height - 20 - (c / max_c) * (height - 40)) for i, c in enumerate(counts)]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#1565c0">'
        f"<title>{_esc(points[i].get('fetched_at'))} — {counts[i]} corrections</title></circle>"
        for i, (x, y) in enumerate(coords)
    )
    axes = (
        f'<line x1="0" y1="{height - 20}" x2="{width}" y2="{height - 20}" stroke="#888"/>'
        f'<line x1="0" y1="0" x2="0" y2="{height - 20}" stroke="#888"/>'
        f'<text x="{width - 4}" y="14" text-anchor="end" font-size="11" fill="#555">'
        f"max {max_c}</text>"
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Corrections over time" style="width:100%;max-width:720px;height:auto">'
        + axes
        + f'<polyline points="{polyline}" fill="none" stroke="#1565c0" stroke-width="2"/>'
        + dots
        + "</svg>"
    )


def render_index(
    report: AnalysisReport,
    corrections: list[dict[str, Any]],
    generated_at: str,
) -> str:
    latency_rows = []
    for lt in report.latencies:
        adv_link = (
            f'<a href="{ADVISORY_URL.format(id=_esc(lt.advisory_id))}">{_esc(lt.advisory_id)}</a>'
            if lt.advisory_id
            else "<em>unmatched</em>"
        )
        latency_rows.append(
            "<tr>"
            f"<td>{_esc(lt.correction_id)}</td>"
            f"<td>{adv_link}</td>"
            f"<td>{_esc(lt.join_method)}</td>"
            f"<td>{_esc(lt.correction_published_at)}</td>"
            f"<td>{_esc(lt.advisory_published_at)}</td>"
            f"<td>{_esc(lt.latency_hours) if lt.latency_hours is not None else '—'}</td>"
            "</tr>"
        )
    latency_table = (
        "<table><thead><tr>"
        f"<th>{_t('Korekta', 'Correction')}</th>"
        f"<th>{_t('Komunikat (advisory)', 'Advisory')}</th>"
        f"<th>{_t('Metoda join', 'Join method')}</th>"
        f"<th>{_t('Korekta opublikowana', 'Correction published')}</th>"
        f"<th>{_t('Komunikat opublikowany', 'Advisory published')}</th>"
        f"<th>{_t('Opóźnienie (h)', 'Latency (h)')}</th>"
        "</tr></thead><tbody>" + "".join(latency_rows) + "</tbody></table>"
        if latency_rows
        else "<p><em>"
        + _t(
            "Brak korekt w najnowszej migawce — rejestr jest pusty.",
            "No corrections in the latest snapshot — the ledger is empty.",
        )
        + "</em></p>"
    )

    ledger_rows = []
    for corr in corrections:
        link_id = _esc(corr.get("id", ""))
        match = corr.get("match_id")
        match_html = (
            f'<a href="{ADVISORY_URL.format(id=_esc(match))}">{_esc(match)}</a>' if match else "—"
        )
        ledger_rows.append(
            "<tr>"
            f'<td><a href="{CORRECTION_URL.format(id=link_id)}">{link_id}</a></td>'
            f"<td>{_esc(corr.get('state', 'unknown'))}</td>"
            f"<td>{match_html}</td>"
            f"<td>{_esc(corr.get('cluster', '—'))}</td>"
            f"<td>{_esc(corr.get('published_at', '—'))}</td>"
            "</tr>"
        )
    ledger_table = (
        "<table><thead><tr>"
        "<th>ID</th>"
        f"<th>{_t('Stan', 'State')}</th>"
        "<th>match_id</th><th>cluster</th>"
        f"<th>{_t('Opublikowano', 'Published at')}</th>"
        "</tr></thead><tbody>" + "".join(ledger_rows) + "</tbody></table>"
        if ledger_rows
        else "<p><em>"
        + _t(
            "Rejestr korekt jest obecnie pusty.",
            "The corrections ledger is currently empty.",
        )
        + "</em></p>"
    )

    stats = report.latency_stats or {}

    def _stat(key: str) -> str:
        val = stats.get(key)
        return _esc(val) if val is not None else "—"

    states_html = ", ".join(
        f"{_esc(k)}: {v}" for k, v in sorted(report.correction_states.items())
    ) or _esc("—")
    latest_health = report.health_timeline[-1] if report.health_timeline else None
    if latest_health and latest_health.classifier_loaded is False:
        health_banner = _t(
            "⚠ Klasyfikator NLP nie jest załadowany — wartości confidence w API LUSTRO pochodzą z "
            "scoringu awaryjnego opartego na słowach kluczowych (keyword-fallback scoring).",
            "⚠ The NLP classifier is not loaded — confidence values in the LUSTRO API currently "
            "come from keyword-fallback scoring.",
        )
        banner_class = "warn"
    elif latest_health and latest_health.classifier_loaded is True:
        health_banner = _t(
            "✓ Klasyfikator NLP jest załadowany — scoring pełny.",
            "✓ The NLP classifier is loaded — full scoring active.",
        )
        banner_class = "ok"
    else:
        health_banner = _t("Stan klasyfikatora nieznany.", "Classifier state unknown.")
        banner_class = "unk"

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LUSTRO Accountability — rejestr korekt i zdrowie API</title>
<style>
:root {{ color-scheme: light; }}
body {{ font-family: system-ui, sans-serif; margin: 0 auto; max-width: 860px; padding: 1rem;
       line-height: 1.55; color: #1a1a1a; background: #fdfdfb; }}
h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.15rem; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.5rem; text-align: left; }}
th {{ background: #f0f0ea; }}
.banner {{ padding: 0.6rem 0.9rem; border-radius: 6px; margin: 0.8rem 0; }}
.banner.warn {{ background: #fff3e0; border: 1px solid #ef6c00; }}
.banner.ok {{ background: #e8f5e9; border: 1px solid #2e7d32; }}
.banner.unk {{ background: #eeeeee; border: 1px solid #9e9e9e; }}
.framing {{ background: #eef3fb; border-left: 4px solid #1565c0; padding: 0.7rem 1rem; }}
.legend {{ font-size: 0.8rem; color: #444; }}
.sw {{ display: inline-block; width: 0.8em; height: 0.8em; border-radius: 2px; margin: 0 0.2em; }}
.sw.ok {{ background: #2e7d32; }} .sw.bad {{ background: #c62828; }}
.sw.unk {{ background: #9e9e9e; }} .sw.flip {{ background: #fff; border: 3px solid #ffca28; }}
.langswitch {{ float: right; }}
button {{ font: inherit; cursor: pointer; }}
footer {{ margin-top: 3rem; font-size: 0.8rem; color: #555; border-top: 1px solid #ddd;
          padding-top: 0.8rem; }}
a {{ color: #0d47a1; }}
code {{ background: #f4f4f0; padding: 0 0.25em; border-radius: 3px; }}
</style>
</head>
<body>
<div class="langswitch">
  <button id="btn-pl" onclick="setLang('pl')">PL</button>
  <button id="btn-en" onclick="setLang('en')">EN</button>
</div>
<h1>{
        _t(
            "LUSTRO Accountability — niezależny monitoring przejrzystości",
            "LUSTRO Accountability — independent transparency monitor",
        )
    }</h1>

<div class="framing">
<p><strong>{_t("Wspierający, niezależny nadzór.", "Supportive, independent oversight.")}</strong>
{
        _t(
            "Ta strona śledzi, jak projekt LUSTRO (projektlustro.eu) dotrzymuje własnych obietnic "
            "przejrzystości: rejestr korekt i zdrowie scoringu. Projekt zasługuje na uznanie za "
            "otwartą konstrukcję korekt — podpisane kryptograficznie rekordy korekt są publicznie "
            "dostępne w API, co czyni ten monitoring w ogóle możliwym.",
            "This page tracks how the LUSTRO project (projektlustro.eu) keeps its own transparency "
            "promises: the corrections ledger and scoring health. The project deserves credit for its "
            "open-corrections design — cryptographically signed correction records are publicly served "
            "by the API, which is what makes this monitor possible at all.",
        )
    }</p>
<p>{
        _t(
            "LUSTRO śledzi narracje, nie osoby. Dane są z założenia zanonimizowane; ta strona nie "
            "próbuje i nie będzie próbować re-identyfikować autorów postów.",
            "LUSTRO tracks narratives, not people. Data is de-identified by design; this page does not "
            "and will not attempt to re-identify post authors.",
        )
    }</p>
</div>

<div class="banner {banner_class}">{health_banner}</div>

<h2>{_t("Rejestr korekt", "Corrections ledger")}</h2>
<p>{_t("Liczba korekt (najnowsza migawka)", "Corrections (latest snapshot)")}:
   <strong>{report.correction_count_latest}</strong> ·
   {_t("stany", "states")}: {states_html}</p>
{ledger_table}

<h2>{_t("Opóźnienie korekt", "Correction latency")}</h2>
<p>{
        _t(
            "Czas od publikacji oryginalnego komunikatu do publikacji korekty. Założenie join: "
            "match_id korekty wskazuje id komunikatu; w przeciwnym razie łączymy po wspólnym UUID "
            "klastra (najwcześniejszy komunikat w klastrze).",
            "Time from publication of the original advisory to publication of the correction. Join "
            "assumption: the correction match_id is the advisory id; otherwise we join on the shared "
            "cluster UUID (earliest advisory in the cluster).",
        )
    }</p>
<p>{_t("Próbka", "Sample")}: {stats.get("count", 0)} · min: {_stat("min_hours")} h ·
   {_t("mediana", "median")}: {_stat("median_hours")} h ·
   max: {_stat("max_hours")} h</p>
{latency_table}

<h2>{_t("Korekty w czasie", "Corrections over time")}</h2>
{_svg_corrections_over_time(report.corrections_over_time)}

<h2>{_t("Oś czasu zdrowia scoringu", "Scoring-health timeline")}</h2>
{_svg_health_timeline(report.health_timeline)}

<footer>
<p>{_t("Wygenerowano", "Generated")}: {_esc(generated_at)} ·
   {_t("migawki", "snapshots")}: {report.snapshot_count} ·
   <a href="https://projektlustro.eu">projektlustro.eu</a> ·
   <a href="https://projektlustro.eu/v1/corrections">/v1/corrections</a> ·
   <a href="https://projektlustro.eu/api/health">/api/health</a></p>
<p>{
        _t(
            "Dane wyłącznie z publicznego API LUSTRO (pola publiczne; bez buforowania pełnych "
            "treści). Migawki append-only przechowywane w repozytorium git.",
            "Data exclusively from the public LUSTRO API (public fields only; no cached full text). "
            "Append-only snapshots stored in the git repository.",
        )
    }</p>
</footer>
<script>
function setLang(l) {{
  document.documentElement.lang = l;
  document.querySelectorAll('[lang="pl"]').forEach(e => e.hidden = l !== 'pl');
  document.querySelectorAll('[lang="en"]').forEach(e => e.hidden = l !== 'en');
}}
</script>
</body>
</html>
"""


def build_site(
    report: AnalysisReport,
    latest_corrections: list[dict[str, Any]],
    generated_at: str,
    out_dir: Path | str = SITE_DIR,
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = out / "index.html"
    index.write_text(render_index(report, latest_corrections, generated_at), encoding="utf-8")
    return index
