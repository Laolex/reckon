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
            f'<tr class="{"changed" if changed else "shared"}">'
            f'<th scope="row"><span class="field-label">{_escape(label)}</span>'
            f'<span class="field-state">{"different" if changed else "shared"}</span></th>'
            f'<td class="field-value">{_escape(left_value)}</td>'
            f'<td class="field-value">{_escape(right_value)}</td></tr>'
        )

    table = "".join(rows)
    left_class = capability_name(divergence.left_capability.available)
    right_class = capability_name(divergence.right_capability.available)
    title = f"{left.get('outcome', 'unknown')} / {right.get('outcome', 'unknown')}"
    comparison_state = "complete" if divergence.explained else "attention"
    comparison_label = "First evidence difference named" if first else "No evidence difference found"
    support = (
        f"The captured fields identify {_escape(first)} as the first recorded divergence."
        if first
        else "The canonical records establish the outcome flip, but no captured field explains it."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reckon investigation — {_escape(title)}</title>
<style>
:root{{--ink:#171815;--paper:#f2eee5;--panel:#e8e1d4;--line:#b9afa0;--muted:#68665f;--accent:#8b5e2c;--danger:#8d3f35;--ok:#3d6755;--sans:Geist,Inter,ui-sans-serif,system-ui,sans-serif;--mono:"Geist Mono","SFMono-Regular",Consolas,monospace}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.45}} code,.eyebrow,.field-state,.metric-label,.step-state,.scope-label{{font-family:var(--mono)}}
header,main,footer{{max-width:1380px;margin:auto;padding-left:clamp(20px,5vw,76px);padding-right:clamp(20px,5vw,76px)}}
header{{padding-top:44px;padding-bottom:34px;border-bottom:1px solid var(--line)}} .eyebrow{{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:var(--accent)}}
h1{{font-size:clamp(38px,6vw,78px);font-weight:560;letter-spacing:-.055em;line-height:.94;max-width:900px;margin:20px 0 16px}} .dek{{max-width:710px;font-size:17px;color:var(--muted);margin:0}}
main{{padding-top:44px;padding-bottom:70px}} .verdict{{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(250px,.7fr);gap:38px;align-items:end;padding-bottom:42px}}
.status{{font-size:clamp(25px,3vw,40px);letter-spacing:-.035em;margin:0}} .status.explained{{color:var(--ok)}} .status.unexplained{{color:var(--danger)}} .explanation{{color:var(--muted);max-width:680px}}
.metric{{border-left:3px solid var(--accent);padding:5px 0 5px 18px}} .metric-label{{display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}} .metric strong{{font-weight:570}}
.proof-steps{{border-top:1px solid var(--ink);margin:0 0 42px;padding:0;list-style:none}} .proof-step{{display:grid;grid-template-columns:38px minmax(180px,.65fr) minmax(0,1fr) auto;gap:18px;align-items:center;padding:15px 0;border-bottom:1px solid var(--line)}}
.step-no{{font-family:var(--mono);font-size:11px;color:var(--muted)}} .step-title{{font-weight:610}} .step-detail{{font-size:13px;color:var(--muted);overflow-wrap:anywhere}} .step-state{{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--ok)}} .step-state.attention{{color:var(--danger)}}
.scope-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:42px}} .scope-card{{background:var(--paper);padding:22px}} .scope-label{{display:block;font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}} .scope-card p{{margin:0;font-size:14px;max-width:58ch}} .scope-card.limit{{border-top:3px solid var(--danger)}} .scope-card.support{{border-top:3px solid var(--ok)}}
.table-scroll{{overflow-x:auto;border-top:1px solid var(--ink)}} .evidence-table{{width:100%;border-collapse:collapse;table-layout:fixed}} .evidence-table thead th{{position:sticky;top:0;background:rgba(242,238,229,.97);border-bottom:1px solid var(--ink);padding:16px 14px;text-align:left;z-index:2}} .evidence-table thead th:first-child{{width:25%}}
.head-label{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.11em}} .decision-head strong{{display:block;font-size:20px;font-weight:570}} .decision-head code{{display:block;font-size:11px;color:var(--muted)}}
.evidence-table tbody th,.evidence-table tbody td{{border-bottom:1px solid var(--line);padding:18px 14px;text-align:left;vertical-align:top}} .evidence-table tbody th{{font-size:13px}} .evidence-table tr.changed th{{border-left:3px solid var(--accent);padding-left:11px}} .field-label{{display:block;font-weight:600}} .field-state{{display:block;font-weight:400;font-size:9px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin-top:4px}} .changed .field-state{{color:var(--accent)}} .field-value{{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}}
.boundary-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:34px;margin-top:62px}} .boundary-grid section{{border-top:1px solid var(--ink);padding-top:20px}} h2{{font-size:22px;letter-spacing:-.025em;margin:0 0 6px}} .boundary-warning{{font-size:13px;color:var(--danger)}} .muted{{font-size:13px;color:var(--muted)}}
.edge-list{{padding:0;list-style:none}} .edge-list li{{display:grid;grid-template-columns:1fr auto 1fr;gap:10px;border-bottom:1px solid var(--line);padding:9px 0;font-size:11px}} .edge-list span{{color:var(--accent)}}
footer{{padding-top:24px;padding-bottom:35px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}}
@media(max-width:760px){{.verdict,.boundary-grid,.scope-grid{{grid-template-columns:1fr}}.proof-step{{grid-template-columns:28px 1fr auto}}.step-detail{{grid-column:2/-1}}.evidence-table{{min-width:720px}}.evidence-table thead th{{position:static}}}}
@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important}}}}
</style>
</head>
<body>
<header><div class="eyebrow">Reckon / canonical evidence comparison</div><h1>What changed between these decisions?</h1><p class="dek">Candidate retrieval nominated the pair. This screen reopens the canonical RCDR records and separates recorded evidence from the conclusion it must explain.</p></header>
<main>
<section class="verdict"><div><p class="status {status_class}">{_escape(status)}</p><p class="explanation">{explanation}</p></div><div class="metric"><span class="metric-label">Guarantee under review</span><strong>{_escape(divergence.guarantee)}</strong></div></section>
<ol class="proof-steps" aria-label="Verification sequence">
<li class="proof-step"><span class="step-no">01</span><span class="step-title">Candidate nominated</span><span class="step-detail">Retrieval found a pair worth investigating; rank is not treated as evidence.</span><span class="step-state">complete</span></li>
<li class="proof-step"><span class="step-no">02</span><span class="step-title">Canonical records reopened</span><span class="step-detail"><code>{_escape(left.get('decision_id'))}</code> and <code>{_escape(right.get('decision_id'))}</code></span><span class="step-state">complete</span></li>
<li class="proof-step"><span class="step-no">03</span><span class="step-title">Captured fields compared</span><span class="step-detail">{comparison_label}</span><span class="step-state {comparison_state}">{comparison_state}</span></li>
<li class="proof-step"><span class="step-no">04</span><span class="step-title">Capability boundary enforced</span><span class="step-detail">{_escape(left_class)} / {_escape(right_class)}; C3 remains outside certification.</span><span class="step-state">complete</span></li>
</ol>
<section class="scope-grid" aria-label="Evidence scope"><div class="scope-card support"><span class="scope-label">Evidence supports</span><p>{support}</p></div><div class="scope-card limit"><span class="scope-label">Evidence does not support</span><p>Candidate rank, uncaptured causes, or counterfactual claims past the first state-coupling edge.</p></div></section>
<div class="table-scroll"><table class="evidence-table"><thead><tr><th class="head-label" scope="col">Recorded field</th><th class="decision-head" scope="col"><strong>{_escape(left.get('outcome'))}</strong><code>{_escape(left.get('decision_id'))}</code></th><th class="decision-head" scope="col"><strong>{_escape(right.get('outcome'))}</strong><code>{_escape(right.get('decision_id'))}</code></th></tr></thead><tbody>{table}</tbody></table></div>
<div class="boundary-grid"><section><h2>{_escape(left_class)}</h2><p class="muted">Left record capability. C3 is never certified.</p>{_boundary(divergence, 'left')}</section><section><h2>{_escape(right_class)}</h2><p class="muted">Right record capability. C3 is never certified.</p>{_boundary(divergence, 'right')}</section></div>
</main>
<footer>Helix may rank candidates. Reckon owns canonical evidence, structural comparison, capability classification, and the C3 boundary.</footer>
</body></html>"""


def write(divergence: Divergence, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(divergence), encoding="utf-8")
    return target
