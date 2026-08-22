"""A standalone proof surface for one canonical RCDR comparison."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .investigate import Divergence, capability_name


def _escape(value: Any) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    if value is None or value == "":
        value = "not recorded"
    return html.escape(str(value))


def _get(record: dict[str, Any], path: str) -> Any:
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _boundary(divergence: Divergence, side: str) -> str:
    value = divergence.left_boundary if side == "left" else divergence.right_boundary
    if value is None:
        return '<p class="muted">Run context was not supplied. No C3 claim is made.</p>'
    if not value.hypothesis:
        return '<p class="muted">No downstream decision reads state written here.</p>'
    edges = "".join(
        f"<li><code>{_escape(writer)}</code><span>{_escape(key)}</span>"
        f"<code>{_escape(reader)}</code></li>"
        for writer, key, reader in value.edges
    )
    return (
        '<p class="boundary-warning">Evidence ends at the first state-coupling edge. '
        "Everything after it is hypothesis, not replay.</p>"
        f'<ol class="edge-list">{edges}</ol>'
    )


def render(divergence: Divergence) -> str:
    first = divergence.first_evidence_divergence
    status = "Explained by captured evidence" if divergence.explained else "Unexplained outcome flip"
    status_class = "explained" if divergence.explained else "unexplained"
    explanation = (
        f"The first recorded divergence is {_escape(first)}."
        if first
        else "No captured evidence field separates these records."
    )
    left = divergence.left
    right = divergence.right
    fields = (
        ("Policy key", "policy.key"),
        ("Resolved value", "policy.resolved_value"),
        ("Provenance", "policy.resolution.provenance"),
        ("Policy source", "policy.resolution.source"),
        ("Policy revision", "policy.resolution.revision"),
        ("Predicate", "predicate.expression"),
        ("Compared value", "compared.value"),
        ("Candidate evidence", "candidates"),
        ("Execution path", "execution.path_digest"),
    )
    rows = []
    for label, path in fields:
        left_value = _get(left, path)
        right_value = _get(right, path)
        changed = left_value != right_value
        rows.append(
            f'<div class="field-row{" changed" if changed else ""}">'
            f'<div class="field-label">{_escape(label)}'
            f'<span>{"different" if changed else "shared"}</span></div>'
            f'<div class="field-value">{_escape(left_value)}</div>'
            f'<div class="field-value">{_escape(right_value)}</div></div>'
        )

    table = "".join(rows)
    left_class = capability_name(divergence.left_capability.available)
    right_class = capability_name(divergence.right_capability.available)
    title = f"{left.get('outcome', 'unknown')} / {right.get('outcome', 'unknown')}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reckon investigation — {_escape(title)}</title>
<style>
:root{{--ink:#171815;--paper:#f2eee5;--panel:#e8e1d4;--line:#b9afa0;--muted:#68665f;--accent:#8b5e2c;--danger:#8d3f35;--ok:#3d6755;--sans:Geist,Inter,ui-sans-serif,system-ui,sans-serif;--mono:"Geist Mono","SFMono-Regular",Consolas,monospace}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.45}} code,.eyebrow,.field-label span,.metric-label{{font-family:var(--mono)}}
header,main,footer{{max-width:1380px;margin:auto;padding-left:clamp(20px,5vw,76px);padding-right:clamp(20px,5vw,76px)}}
header{{padding-top:44px;padding-bottom:34px;border-bottom:1px solid var(--line)}} .eyebrow{{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:var(--accent)}}
h1{{font-size:clamp(38px,6vw,78px);font-weight:560;letter-spacing:-.055em;line-height:.94;max-width:900px;margin:20px 0 16px}} .dek{{max-width:710px;font-size:17px;color:var(--muted);margin:0}}
main{{padding-top:44px;padding-bottom:70px}} .verdict{{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(250px,.7fr);gap:38px;align-items:end;padding-bottom:42px}}
.status{{font-size:clamp(25px,3vw,40px);letter-spacing:-.035em;margin:0}} .status.explained{{color:var(--ok)}} .status.unexplained{{color:var(--danger)}} .explanation{{color:var(--muted);max-width:680px}}
.metric{{border-left:3px solid var(--accent);padding:5px 0 5px 18px}} .metric-label{{display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}} .metric strong{{font-weight:570}}
.heads,.field-row{{display:grid;grid-template-columns:minmax(150px,.5fr) repeat(2,minmax(0,1fr));column-gap:28px}} .heads{{position:sticky;top:0;background:rgba(242,238,229,.97);border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);padding:16px 0;z-index:2}}
.head-label{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.11em}} .decision-head strong{{display:block;font-size:20px;font-weight:570}} .decision-head code{{font-size:11px;color:var(--muted)}}
.field-row{{border-bottom:1px solid var(--line);padding:19px 0}} .field-row.changed{{border-left:3px solid var(--accent);padding-left:14px}} .field-label{{font-size:13px;font-weight:600}} .field-label span{{display:block;font-weight:400;font-size:9px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin-top:4px}} .field-value{{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}}
.boundary-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:34px;margin-top:62px}} .boundary-grid section{{border-top:1px solid var(--ink);padding-top:20px}} h2{{font-size:22px;letter-spacing:-.025em;margin:0 0 6px}} .boundary-warning{{font-size:13px;color:var(--danger)}} .muted{{font-size:13px;color:var(--muted)}}
.edge-list{{padding:0;list-style:none}} .edge-list li{{display:grid;grid-template-columns:1fr auto 1fr;gap:10px;border-bottom:1px solid var(--line);padding:9px 0;font-size:11px}} .edge-list span{{color:var(--accent)}}
footer{{padding-top:24px;padding-bottom:35px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}}
@media(max-width:760px){{.verdict,.boundary-grid{{grid-template-columns:1fr}}.heads,.field-row{{grid-template-columns:1fr 1fr;gap:10px}}.heads>.head-label,.field-label{{grid-column:1/-1}}.heads{{position:static}}}}
@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important}}}}
</style>
</head>
<body>
<header><div class="eyebrow">Reckon / canonical evidence comparison</div><h1>What changed between these decisions?</h1><p class="dek">Candidate retrieval nominated the pair. This screen reopens the canonical RCDR records and separates recorded evidence from the conclusion it must explain.</p></header>
<main>
<section class="verdict"><div><p class="status {status_class}">{_escape(status)}</p><p class="explanation">{explanation}</p></div><div class="metric"><span class="metric-label">Guarantee under review</span><strong>{_escape(divergence.guarantee)}</strong></div></section>
<div class="heads"><div class="head-label">Recorded field</div><div class="decision-head"><strong>{_escape(left.get('outcome'))}</strong><code>{_escape(left.get('decision_id'))}</code></div><div class="decision-head"><strong>{_escape(right.get('outcome'))}</strong><code>{_escape(right.get('decision_id'))}</code></div></div>
{table}
<div class="boundary-grid"><section><h2>{_escape(left_class)}</h2><p class="muted">Left record capability. C3 is never certified.</p>{_boundary(divergence, 'left')}</section><section><h2>{_escape(right_class)}</h2><p class="muted">Right record capability. C3 is never certified.</p>{_boundary(divergence, 'right')}</section></div>
</main>
<footer>Helix may rank candidates. Reckon owns canonical evidence, structural comparison, capability classification, and the C3 boundary.</footer>
</body></html>"""


def write(divergence: Divergence, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(divergence), encoding="utf-8")
    return target
