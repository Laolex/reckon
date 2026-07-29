"""Static site generator for the public registry.

Every page is a file. No server, no database, no API — which is not a shortcut but the
argument: a credential that only its issuer can serve is a claim about a claim. The
generator reads ledgers and writes HTML; `assets/verify.js` lets any reader re-derive
every figure in their own browser from the raw record shipped alongside it.

Pages backed by real records: the registry, an agent's credential, one commitment,
the raw chain, and the open-commitment board. Pages whose machinery does not exist yet
— launch, feed, standings — are generated as marked stubs so the product's shape can be
reviewed, and every fabricated figure on them carries a SAMPLE chip.
"""

import json
import re
import shutil
from dataclasses import dataclass
from html import escape
from pathlib import Path

from .credential import Credential, project
from .integrity import IntegrityReport
from .ledger import read
from .view import LedgerView, ledger_view

ASSETS = Path(__file__).resolve().parent / "assets"

EVIDENCE_LABELS = {
    "A": "Cryptographic proof",
    "B": "Third-party receipt",
    "C": "Counterparty attestation",
    "D": "Self-attestation",
}

CELL_CHIPS = {
    "attributable": ("Earned", "Did the work and got the result"),
    "competent_unsuccessful": ("Executed, missed", "Did the work, result did not come"),
    "luck": ("Luck", "Result came, the work was not done"),
    "failure": ("Failed", "Work not done, result not achieved"),
    "indeterminate": ("Unsettled", "Could not be settled either way"),
}

NAV = [
    ("", "Registry", "index.html"),
    ("open", "Open board", "open.html"),
    ("verify", "Verify", "verify.html"),
    ("launch", "Launch", "launch.html"),
    ("feed", "Feed", "feed.html"),
    ("standings", "Standings", "standings.html"),
]

STUB_PAGES = {"launch", "feed", "standings"}


# --------------------------------------------------------------------------- css

CSS = """
:root{
  --ground:#101418; --raised:#171c22; --sunk:#0b0e11; --hair:#262d35;
  --ink:#dfe3e6; --muted:#7d868f; --dim:#5a626b;
  --brass:#c9973f; --brass-dim:#8a6f37;
  --verdigris:#4c9c7a; --oxide:#cc5540;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
@media (prefers-color-scheme: light){
  :root{
    --ground:#f1efeb; --raised:#f8f7f4; --sunk:#e6e3dd; --hair:#d5d1c9;
    --ink:#15191d; --muted:#5d646c; --dim:#868d95;
    --brass:#8a6420; --brass-dim:#9a7a3a;
    --verdigris:#2f6f53; --oxide:#a8422f;
  }
}
:root[data-theme="light"]{
  --ground:#f1efeb; --raised:#f8f7f4; --sunk:#e6e3dd; --hair:#d5d1c9;
  --ink:#15191d; --muted:#5d646c; --dim:#868d95;
  --brass:#8a6420; --brass-dim:#9a7a3a;
  --verdigris:#2f6f53; --oxide:#a8422f;
}
:root[data-theme="dark"]{
  --ground:#101418; --raised:#171c22; --sunk:#0b0e11; --hair:#262d35;
  --ink:#dfe3e6; --muted:#7d868f; --dim:#5a626b;
  --brass:#c9973f; --brass-dim:#8a6f37;
  --verdigris:#4c9c7a; --oxide:#cc5540;
}

*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:inherit}
a:focus-visible,button:focus-visible,textarea:focus-visible{outline:2px solid var(--brass);
  outline-offset:2px}

.shell{display:grid;grid-template-columns:1fr;gap:0;min-height:100vh}
@media (min-width:60rem){.shell{grid-template-columns:15rem 1fr}}

/* ---- rail ---- */
.rail{border-bottom:1px solid var(--hair);padding:1.5rem 1.25rem;
  display:flex;flex-direction:column;gap:1.5rem;background:var(--sunk)}
@media (min-width:60rem){
  .rail{border-bottom:0;border-right:1px solid var(--hair);
    position:sticky;top:0;height:100vh;padding:2rem 1.5rem}
}
.mark{font-family:var(--mono);font-size:.9rem;letter-spacing:.22em;text-transform:uppercase;
  font-weight:600;text-decoration:none;color:var(--ink)}
.mark em{color:var(--brass);font-style:normal}
.tagline{font-size:.74rem;color:var(--dim);line-height:1.5;margin-top:.4rem;
  font-family:var(--mono)}
.rail nav{display:flex;flex-wrap:wrap;gap:.15rem}
@media (min-width:60rem){.rail nav{flex-direction:column;flex-wrap:nowrap}}
.rail nav a{font-family:var(--mono);font-size:.76rem;letter-spacing:.09em;
  text-transform:uppercase;text-decoration:none;color:var(--muted);
  padding:.45rem .6rem;border-left:2px solid transparent;display:flex;
  justify-content:space-between;gap:.5rem;align-items:center}
.rail nav a:hover{color:var(--ink);background:var(--raised)}
.rail nav a[aria-current]{color:var(--brass);border-left-color:var(--brass);
  background:var(--raised)}
.rail nav a .wip{font-size:.6rem;letter-spacing:.1em;color:var(--dim);
  border:1px solid var(--hair);padding:0 .25rem;border-radius:2px}

/* ---- main ---- */
main{padding:2rem 1.25rem 5rem;min-width:0}
@media (min-width:60rem){main{padding:3.5rem 3rem 6rem}}
.col{max-width:54rem;display:flex;flex-direction:column;gap:2.5rem}

.eyebrow{font-family:var(--mono);font-size:.68rem;letter-spacing:.2em;
  text-transform:uppercase;color:var(--muted)}
h1{font-family:var(--mono);font-size:clamp(1.4rem,3.4vw,2rem);letter-spacing:-.01em;
  margin:.5rem 0 0;font-weight:600;text-wrap:balance;word-break:break-word}
h2{font-family:var(--mono);font-size:.8rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);margin:0;font-weight:600}
p{margin:0}
.prose{max-width:60ch;display:flex;flex-direction:column;gap:.85rem}
.prose a{color:var(--brass)}
section{display:flex;flex-direction:column;gap:1rem}

.hash{font-family:var(--mono);color:var(--brass);word-break:break-all;font-size:.8rem}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}

/* ---- status ---- */
.status{display:inline-flex;align-items:center;gap:.5rem;font-family:var(--mono);
  font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;font-weight:600}
.status::before{content:"";width:.5rem;height:.5rem;border-radius:50%;
  background:currentColor;flex:none}
.status-ok{color:var(--verdigris)}
.status-bad{color:var(--oxide)}

/* ---- tables ---- */
.scroll{overflow-x:auto;border:1px solid var(--hair);border-radius:2px;
  background:var(--raised)}
table{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:.8rem}
thead th{text-align:left;font-size:.66rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);font-weight:600;padding:.7rem .85rem;
  border-bottom:1px solid var(--hair);white-space:nowrap;background:var(--sunk)}
tbody td{padding:.65rem .85rem;border-bottom:1px solid var(--hair);
  font-variant-numeric:tabular-nums;vertical-align:top}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--sunk)}
td.right,th.right{text-align:right}
td a{color:var(--brass);text-decoration:none}
td a:hover{text-decoration:underline}
.zero{color:var(--dim)}

/* ---- key/value ---- */
.kv{display:grid;grid-template-columns:1fr;gap:0;border:1px solid var(--hair);
  border-radius:2px;background:var(--raised);overflow:hidden}
.kv div{display:grid;grid-template-columns:1fr;gap:.15rem;padding:.75rem .9rem;
  border-bottom:1px solid var(--hair)}
@media (min-width:38rem){.kv div{grid-template-columns:12rem 1fr;gap:1rem;align-items:baseline}}
.kv div:last-child{border-bottom:0}
.kv dt, .kv .k{font-family:var(--mono);font-size:.66rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted)}
.kv .v{font-family:var(--mono);font-size:.82rem;word-break:break-word}

/* ---- chips ---- */
.chip{display:inline-block;font-family:var(--mono);font-size:.66rem;letter-spacing:.1em;
  text-transform:uppercase;padding:.15rem .45rem;border-radius:2px;
  border:1px solid var(--hair);color:var(--muted);white-space:nowrap}
.chip-earned{color:var(--verdigris);border-color:var(--verdigris)}
.chip-luck{color:var(--brass);border-color:var(--brass)}
.chip-failed{color:var(--oxide);border-color:var(--oxide)}
.chip-open{color:var(--muted)}
.chip-sample{color:var(--brass);border-color:var(--brass-dim);
  background:color-mix(in srgb,var(--brass) 12%,transparent)}

/* ---- the chain spine ---- */
.chain{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.chain li{display:grid;grid-template-columns:2.25rem 1fr;gap:0;position:relative;
  padding-bottom:1.1rem}
.chain li:last-child{padding-bottom:0}
.chain .spine{position:relative}
.chain .spine::before{content:"";position:absolute;left:.5rem;top:.55rem;
  width:.5rem;height:.5rem;border-radius:50%;background:var(--brass);
  box-shadow:0 0 0 3px var(--ground)}
.chain li:not(:last-child) .spine::after{content:"";position:absolute;
  left:.72rem;top:1.15rem;bottom:-1.1rem;width:1px;background:var(--brass-dim)}
.chain li.break .spine::after{background:repeating-linear-gradient(
  to bottom,var(--oxide) 0 3px,transparent 3px 7px)}
.chain li.break .spine::before{background:var(--oxide)}
.chain .card{border:1px solid var(--hair);border-radius:2px;background:var(--raised);
  padding:.7rem .9rem;display:flex;flex-direction:column;gap:.3rem;min-width:0}
.chain li.break .card{border-color:var(--oxide)}
.chain .head{display:flex;flex-wrap:wrap;gap:.5rem;align-items:baseline;
  font-family:var(--mono);font-size:.74rem}
.chain .seqno{color:var(--muted);letter-spacing:.1em}
.chain .kind{letter-spacing:.12em;text-transform:uppercase;font-weight:600}
.chain .detail{font-family:var(--mono);font-size:.78rem;color:var(--ink);
  word-break:break-word}
.chain .meta{font-family:var(--mono);font-size:.7rem;color:var(--dim);
  word-break:break-all}
.chain .withheld{color:var(--dim);font-style:italic}
.breakline{font-family:var(--mono);font-size:.72rem;color:var(--oxide);
  letter-spacing:.06em;padding:.15rem 0 .5rem}

/* ---- callouts ---- */
.broken{border:1px solid var(--oxide);border-left-width:3px;border-radius:2px;
  padding:1rem 1.1rem;display:flex;flex-direction:column;gap:.6rem;
  background:color-mix(in srgb,var(--oxide) 7%,transparent)}
.broken pre{margin:0;font-family:var(--mono);font-size:.76rem;overflow-x:auto;
  white-space:pre-wrap;color:var(--ink)}
.note{font-size:.86rem;color:var(--muted);max-width:60ch}

.stub{border:1px solid var(--brass-dim);border-radius:2px;overflow:hidden}
.stub .band{background:repeating-linear-gradient(135deg,
  color-mix(in srgb,var(--brass) 16%,transparent) 0 10px,transparent 10px 20px);
  padding:.85rem 1.1rem;border-bottom:1px solid var(--brass-dim);
  font-family:var(--mono);font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--brass);font-weight:600}
.stub .inner{padding:1.1rem;display:flex;flex-direction:column;gap:.7rem}
.stub .inner p{font-size:.88rem;color:var(--muted);max-width:60ch}
.stub .inner strong{color:var(--ink)}

/* ---- verify tool ---- */
.tool{display:flex;flex-direction:column;gap:.9rem}
textarea{width:100%;min-height:11rem;background:var(--sunk);color:var(--ink);
  border:1px solid var(--hair);border-radius:2px;padding:.85rem;
  font-family:var(--mono);font-size:.78rem;line-height:1.5;resize:vertical}
.actions{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center}
button{font-family:var(--mono);font-size:.74rem;letter-spacing:.12em;
  text-transform:uppercase;font-weight:600;padding:.6rem 1.1rem;border-radius:2px;
  border:1px solid var(--brass);background:var(--brass);color:var(--sunk);
  cursor:pointer}
button:hover{filter:brightness(1.08)}
button.ghost{background:transparent;color:var(--muted);border-color:var(--hair)}
button.ghost:hover{color:var(--ink)}
#out:empty{display:none}
.offline{font-family:var(--mono);font-size:.7rem;color:var(--dim);letter-spacing:.06em}

footer{border-top:1px solid var(--hair);margin-top:1rem;padding-top:1.5rem;
  font-family:var(--mono);font-size:.7rem;color:var(--dim);line-height:1.8;
  display:flex;flex-direction:column;gap:.2rem}
footer a{color:var(--brass-dim)}

@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""


# ------------------------------------------------------------------- primitives

def _slug(value: str) -> str:
    """A filesystem- and URL-safe stem. Refuses anything that could escape the tree."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not cleaned or cleaned in (".", ".."):
        raise ValueError(f"{value!r} does not yield a usable path segment")
    return cleaned


def _e(value) -> str:
    return escape(str(value), quote=True)


def _short(seal: str, keep: int = 10) -> str:
    """Abbreviate `sha256:abcdef…` for display without ever showing a truncated hash
    as if it were whole — the ellipsis is the point."""
    algo, _, body = seal.partition(":")
    if not body or len(body) <= keep:
        return seal
    return f"{algo}:{body[:keep]}\u2026"


def _when(stamp: str | None) -> str:
    """Timestamps to the second. Sub-second precision is noise on a page, and the
    full-precision value stays in the downloadable record where it belongs."""
    if not stamp:
        return "\u2014"
    head, dot, _ = stamp.partition(".")
    return f"{head}Z" if dot else stamp


def _chip(cell: str | None) -> str:
    if cell is None:
        return '<span class="chip chip-open">Open</span>'
    label, title = CELL_CHIPS[cell]
    css = {"attributable": "chip-earned", "luck": "chip-luck",
           "failure": "chip-failed", "competent_unsuccessful": "chip-earned"}.get(cell, "")
    return f'<span class="chip {css}" title="{_e(title)}">{_e(label)}</span>'


def _status(report: IntegrityReport) -> str:
    if report.intact:
        return '<span class="status status-ok">Record intact</span>'
    return '<span class="status status-bad">Record broken</span>'


def _kv(pairs: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<div><span class="k">{_e(k)}</span><span class="v">{v}</span></div>'
        for k, v in pairs
    )
    return f'<div class="kv">{rows}</div>'


def layout(title: str, active: str, body: str, root: str) -> str:
    nav = "".join(
        '<a href="{href}"{cur}>{label}{wip}</a>'.format(
            href=_e(root + href),
            cur=' aria-current="page"' if key == active else "",
            label=_e(label),
            wip='<span class="wip">stub</span>' if key in STUB_PAGES else "",
        )
        for key, label, href in NAV
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title>
<link rel="stylesheet" href="{_e(root)}assets/site.css">
</head><body>
<div class="shell">
<aside class="rail">
  <div>
    <a class="mark" href="{_e(root)}index.html">Reck<em>o</em>n</a>
    <div class="tagline">Registry of sealed<br>commitments</div>
  </div>
  <nav>{nav}</nav>
</aside>
<main><div class="col">
{body}
<footer>
  <span>Every figure on this site is a count folded from an append-only record.
  Nothing is a rate.</span>
  <span>No server is involved. <a href="{_e(root)}verify.html">Re-verify any record
  in your own browser.</a></span>
</footer>
</div></main>
</div></body></html>
"""


# ------------------------------------------------------------------------ pages

@dataclass
class AgentBundle:
    agent: str
    slug: str
    records: list[dict]
    credential: Credential
    view: LedgerView


def registry_page(bundles: list[AgentBundle]) -> str:
    if not bundles:
        rows = '<tr><td colspan="6" class="zero">No ledgers found.</td></tr>'
    else:
        rows = ""
        for b in bundles:
            c = b.credential
            if c.integrity.intact:
                def cell(n: int) -> str:
                    return f'<td class="right">{n}</td>' if n else \
                           '<td class="right zero">0</td>'
                figures = (cell(c.commitments) + cell(c.unopened) + cell(c.declines)
                           + f"<td>{_e(c.completeness)}</td>")
            else:
                # A broken record publishes no counts here either. Showing them beside
                # the warning is how a reader ends up remembering the number.
                figures = '<td class="right zero">—</td>' * 3 + '<td class="zero">—</td>'
            rows += (
                f"<tr>"
                f'<td><a href="a/{_e(b.slug)}/index.html">{_e(b.agent)}</a></td>'
                f"<td>{_status(c.integrity)}</td>"
                f"{figures}"
                f"</tr>"
            )

    sound = [b for b in bundles if b.credential.integrity.intact]
    total_open = sum(len(b.view.open_commitments) for b in sound)
    return f"""
<header>
  <div class="eyebrow">The registry</div>
  <h1>{len(bundles)} agent{"" if len(bundles) == 1 else "s"} on the record</h1>
</header>
<div class="prose">
  <p>Each row is an append-only ledger. A commitment enters it sealed, before its
  outcome is known, and is judged on two separate questions once the horizon passes:
  was the obligation met, and did the outcome arrive. Those are different questions,
  and keeping them apart is the entire point — an agent that got a good result without
  doing the work it promised earns nothing here.</p>
  <p>There are <strong>{total_open}</strong> commitments currently open across the
  registry. <a href="open.html">See the board.</a></p>
</div>
<section>
  <h2>Ledgers</h2>
  <div class="scroll"><table>
    <thead><tr>
      <th>Agent</th><th>Integrity</th><th class="right">On record</th>
      <th class="right">Unopened seals</th><th class="right">Declines</th>
      <th>Completeness</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="note">“Unopened seals” counts commitments sealed but never disclosed. It is
  published because it is the figure that makes cherry-picking visible: a hundred seals
  against twelve disclosures says more than any hit rate.</p>
</section>
"""


def credential_page(b: AgentBundle) -> str:
    c = b.credential
    if not c.integrity.intact:
        detail = _e(c.integrity.render())
        body = f"""
<div class="broken">
  <span class="status status-bad">Record broken — figures unreportable</span>
  <pre>{detail}</pre>
  <p class="note">No counts are shown. A number printed beside a warning is still a
  number, and readers keep the number. The raw record is published anyway so anyone can
  confirm this verdict themselves.</p>
</div>
<section>
  <h2>The record itself</h2>
  <div class="prose"><p><a href="ledger.html">Read the chain</a> ·
  <a href="{_e(b.slug)}.jsonl">Download the raw ledger</a> ·
  <a href="../../verify.html">Verify it in your browser</a></p></div>
</section>
"""
        return f"""
<header>
  <div class="eyebrow">Credential</div>
  <h1>{_e(b.agent)}</h1>
</header>
{body}
"""

    activity = _kv([
        ("Commitments", f'<span class="num">{c.commitments}</span>'),
        ("Resolved", f'<span class="num">{c.resolved}</span>'),
        ("Still open", f'<span class="num">{c.unresolved}</span>'),
        ("Sealed, never opened", f'<span class="num">{c.unopened}</span>'),
        ("Declined openly", f'<span class="num">{c.declines}</span>'),
        ("Completeness", _e(c.completeness)),
        ("Record begins", _e(_when(c.genesis))),
    ])

    cell_rows = ""
    for name, count in c.cells.items():
        _, meaning = CELL_CHIPS[name]
        cell_rows += (
            f"<tr><td>{_chip(name)}</td><td>{_e(meaning)}</td>"
            f'<td class="right">{count if count else "<span class=zero>0</span>"}</td></tr>'
        )

    ev_rows = ""
    for name, count in c.evidence_mix.items():
        ev_rows += (
            f'<tr><td class="num">Class {_e(name)}</td>'
            f"<td>{_e(EVIDENCE_LABELS[name])}</td>"
            f'<td class="right">{count if count else "<span class=zero>0</span>"}</td></tr>'
        )

    commitment_rows = ""
    for item in b.view.commitments:
        commitment_rows += (
            f"<tr>"
            f'<td><a href="c/{_e(_slug(item.commitment_id))}.html">'
            f"{_e(item.commitment_id)}</a></td>"
            f"<td>{_e(item.objective)}</td>"
            f'<td class="num">{_e(item.horizon[:10])}</td>'
            f'<td class="num">{_e(item.obligation["evidence_class"])}</td>'
            f"<td>{_chip(item.cell)}</td>"
            f"</tr>"
        )
    if not commitment_rows:
        commitment_rows = '<tr><td colspan="5" class="zero">Nothing disclosed yet.</td></tr>'

    unopened_note = ""
    if c.unopened:
        unopened_note = (
            f'<p class="note">{c.unopened} further commitment'
            f'{"" if c.unopened == 1 else "s"} {"is" if c.unopened == 1 else "are"} '
            "sealed and not yet disclosed. Their contents are unknown even to this "
            "site — only the seal and the moment it was written are on the record.</p>"
        )

    return f"""
<header>
  <div class="eyebrow">Credential</div>
  <h1>{_e(b.agent)}</h1>
</header>
<div>{_status(c.integrity)}</div>
<section>
  <h2>Activity</h2>
  {activity}
  {unopened_note}
</section>
<section>
  <h2>Obligation against outcome</h2>
  <div class="scroll"><table>
    <thead><tr><th>Verdict</th><th>Meaning</th><th class="right">Count</th></tr></thead>
    <tbody>{cell_rows}</tbody>
  </table></div>
  <p class="note">Two verdicts per commitment, never merged into one. “Luck” is the
  case an outcome-only credential cannot see, and it earns no credit.</p>
</section>
<section>
  <h2>Evidence behind the obligations</h2>
  <div class="scroll"><table>
    <thead><tr><th>Class</th><th>Kind</th><th class="right">Count</th></tr></thead>
    <tbody>{ev_rows}</tbody>
  </table></div>
  <p class="note">Classified, never scored. A self-attested obligation is not worth
  fewer points than a cryptographic one — it is a different kind of thing, and the
  reader is told which they are looking at.</p>
</section>
<section>
  <h2>Disclosed commitments</h2>
  <div class="scroll"><table>
    <thead><tr><th>ID</th><th>Objective</th><th>Horizon</th><th>Ev.</th>
    <th>Verdict</th></tr></thead>
    <tbody>{commitment_rows}</tbody>
  </table></div>
</section>
<section>
  <h2>Check this yourself</h2>
  <div class="prose"><p><a href="ledger.html">Read the chain</a> ·
  <a href="{_e(b.slug)}.jsonl">Download the raw ledger</a> ·
  <a href="../../verify.html">Verify it in your browser</a></p></div>
</section>
"""


def commitment_page(b: AgentBundle, item) -> str:
    seal_pairs = [
        ("Commitment ID", _e(item.commitment_id)),
        ("Seal", f'<span class="hash">{_e(item.seal)}</span>'),
    ]
    if item.was_sealed_before_disclosure:
        seal_pairs += [
            ("Sealed at", f'{_e(_when(item.sealed_at))} <span class="chip">seq '
                          f'{item.sealed_seq}</span>'),
            ("Disclosed at", f'{_e(_when(item.disclosed_at))} <span class="chip">seq '
                             f'{item.disclosed_seq}</span>'),
        ]
    else:
        seal_pairs += [
            ("Written at", f'{_e(_when(item.disclosed_at))} <span class="chip">seq '
                           f'{item.disclosed_seq}</span>'),
        ]
    seal_pairs += [("Horizon", _e(item.horizon))]

    terms = _kv([
        ("Objective", _e(item.objective)),
        ("Obligation", _e(item.obligation["statement"])),
        ("Obligation met when", _e(item.obligation_criteria)),
        ("Outcome achieved when", _e(item.outcome_criteria)),
        ("Evidence class",
         f'<span class="num">{_e(item.obligation["evidence_class"])}</span> — '
         f'{_e(EVIDENCE_LABELS[item.obligation["evidence_class"]])}'),
        ("Witnessed by", _e(item.obligation["evidence_source"])),
        ("Sources", _e(", ".join(item.sources)) or "—"),
    ])

    if item.resolution:
        r = item.resolution
        evidence = "".join(
            f'<div><span class="k">{_e(k)}</span><span class="v">{_e(v)}</span></div>'
            for k, v in r["evidence_seen"].items()
        )
        label, meaning = CELL_CHIPS[item.cell]
        outcome = f"""
<section>
  <h2>Resolution</h2>
  {_kv([
      ("Obligation", f'<strong>{_e(r["obligation_verdict"])}</strong>'),
      ("Outcome", f'<strong>{_e(r["outcome_verdict"])}</strong>'),
      ("Attribution", f'{_chip(item.cell)} {_e(meaning)}'),
  ])}
  <h2>Evidence the resolver saw</h2>
  <div class="kv">{evidence}</div>
  <p class="note">A verdict with no evidence recorded beside it is an opinion, so the
  writer refuses to record one.</p>
</section>
"""
    else:
        outcome = f"""
<section>
  <h2>Resolution</h2>
  <div class="prose"><p>Not yet resolved. The horizon is
  <span class="num">{_e(item.horizon)}</span>, after which both questions get answered
  against the evidence source named above.</p></div>
</section>
"""

    provenance = (
        "<p>This commitment was <strong>sealed before it was readable</strong>. The hash "
        f"was written at sequence {item.sealed_seq} and the text only became public at "
        f"sequence {item.disclosed_seq} — so the terms could not have been adjusted to "
        "fit what happened in between.</p>"
        if item.was_sealed_before_disclosure else
        "<p>This commitment was written in the clear rather than sealed first, so it "
        "carries no proof that it predates knowledge of the outcome beyond its position "
        "in the chain.</p>"
    )

    return f"""
<header>
  <div class="eyebrow"><a href="../index.html">{_e(b.agent)}</a> · commitment</div>
  <h1>{_e(item.objective)}</h1>
</header>
<div>{_chip(item.cell)}</div>
<section>
  <h2>Provenance</h2>
  <div class="prose">{provenance}</div>
  {_kv(seal_pairs)}
</section>
<section>
  <h2>Terms as sealed</h2>
  {terms}
  <p class="note">Every field above is covered by the seal. Changing any one of them
  changes the hash, which is why the record can be published without being trusted.</p>
</section>
{outcome}
"""


def ledger_page(b: AgentBundle) -> str:
    report = b.credential.integrity
    forks = set(report.forks)
    gap_at = {hi for _, hi in report.gaps}

    items = ""
    for record in b.records:
        seq = record["seq"]
        kind = record.get("kind", "unknown")
        broken = seq in forks or seq in gap_at
        cls = ' class="break"' if broken else ""

        if kind == "sealed_commitment":
            detail = '<span class="withheld">payload withheld until reveal</span>'
        elif kind == "decline":
            detail = _e(record.get("reason", ""))
        elif kind == "resolution":
            detail = (f'{_e(record["commitment_id"])} — obligation '
                      f'<strong>{_e(record["obligation_verdict"])}</strong>, outcome '
                      f'<strong>{_e(record["outcome_verdict"])}</strong>')
        elif kind in ("commitment", "reveal"):
            detail = f'{_e(record["commitment_id"])} — {_e(record["objective"])}'
        else:
            detail = ""

        note = ""
        if seq in gap_at:
            note = '<div class="breakline">sequence jumps — a record is missing here</div>'
        elif seq in forks:
            note = '<div class="breakline">this record does not link to its predecessor</div>'

        seal = record.get("seal")
        meta = f'seal {_short(seal)} · ' if seal else ""
        items += f"""<li{cls}>
  <div class="spine"></div>
  <div class="card">
    <div class="head"><span class="seqno">SEQ {seq:03d}</span>
    <span class="kind">{_e(kind.replace("_", " "))}</span></div>
    <div class="detail">{detail}</div>
    <div class="meta">{meta}prev {_short(record["prev_hash"], 8)}</div>
    {note}
  </div>
</li>"""

    return f"""
<header>
  <div class="eyebrow"><a href="index.html">{_e(b.agent)}</a> · the chain</div>
  <h1>{len(b.records)} records</h1>
</header>
<div>{_status(report)}</div>
<div class="prose">
  <p>Each record names the hash of the one before it, so nothing can be edited without
  breaking the line. Each also carries a sequence number, so nothing can be
  <em>removed</em> without leaving a hole. The second detector is the one that matters:
  agents do not rewrite bad months, they stop writing.</p>
</div>
<ol class="chain">{items}</ol>
<section>
  <h2>Raw</h2>
  <div class="prose"><p><a href="{_e(b.slug)}.jsonl">Download this ledger</a> and
  <a href="../../verify.html">check it yourself</a> — the verifier runs in your browser
  and never sends the file anywhere.</p></div>
</section>
"""


def open_page(bundles: list[AgentBundle]) -> str:
    rows = ""
    pending = []
    sound = [b for b in bundles if b.credential.integrity.intact]
    excluded = len(bundles) - len(sound)
    for b in sound:
        for item in b.view.open_commitments:
            pending.append((item.horizon, b, item))
    pending.sort(key=lambda t: t[0])

    for horizon, b, item in pending:
        rows += (
            f"<tr>"
            f'<td class="num">{_e(horizon[:10])}</td>'
            f'<td><a href="a/{_e(b.slug)}/index.html">{_e(b.agent)}</a></td>'
            f'<td><a href="a/{_e(b.slug)}/c/{_e(_slug(item.commitment_id))}.html">'
            f"{_e(item.objective)}</a></td>"
            f"<td>{_e(item.obligation['statement'])}</td>"
            f'<td class="num">{_e(item.obligation["evidence_class"])}</td>'
            f"</tr>"
        )
    if not rows:
        rows = '<tr><td colspan="5" class="zero">Nothing open right now.</td></tr>'

    sealed_total = sum(b.credential.unopened for b in sound)
    return f"""
<header>
  <div class="eyebrow">Open board</div>
  <h1>{len(pending)} commitment{"" if len(pending) == 1 else "s"} awaiting judgement</h1>
</header>
<div class="prose">
  <p>Forward-looking, which is the only honest way to read a track record. Every line
  below was sealed before its outcome was known and has not yet been resolved — so
  nobody, including us, knows how it turns out.</p>
  <p>A further <strong>{sealed_total}</strong> commitment{"" if sealed_total == 1 else "s"}
  {"is" if sealed_total == 1 else "are"} sealed but not disclosed, and so cannot be
  listed here at all.</p>
  {f"<p>{excluded} ledger{'' if excluded == 1 else 's'} " + ("is" if excluded == 1 else "are") + " left out of this board entirely, because " + ("its" if excluded == 1 else "their") + " chain is broken. Nothing read from a record with a hole in it belongs on a page about what happens next.</p>" if excluded else ""}
</div>
<section>
  <h2>Open, sorted by horizon</h2>
  <div class="scroll"><table>
    <thead><tr><th>Horizon</th><th>Agent</th><th>Objective</th><th>Obligation</th>
    <th>Ev.</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</section>
"""


def verify_page(sample_agent: str | None, sample_path: str | None) -> str:
    sample = ""
    if sample_path:
        sample = (f'<button class="ghost" id="load-sample" '
                  f'data-src="{_e(sample_path)}">Load {_e(sample_agent)}</button>')
    return f"""
<header>
  <div class="eyebrow">Verify</div>
  <h1>Check a record without trusting us</h1>
</header>
<div class="prose">
  <p>Paste a ledger below, or drop the file in. It is parsed, rehashed and checked
  entirely inside this page — the file never leaves your machine, and you can confirm
  that by turning off your network before pressing the button.</p>
  <p>The verifier recomputes every seal from the disclosed fields, walks the hash chain,
  looks for holes in the sequence, and matches each disclosure against a seal that was
  written earlier. It is the same algorithm the writer uses, reimplemented
  independently; the two are held byte-identical by a cross-language test.</p>
</div>
<section class="tool">
  <textarea id="in" spellcheck="false"
    placeholder="One JSON object per line…" aria-label="Ledger contents"></textarea>
  <div class="actions">
    <button id="run">Verify</button>
    {sample}
    <button class="ghost" id="clear">Clear</button>
    <span class="offline" id="net"></span>
  </div>
  <div id="out"></div>
</section>
<script src="assets/verify.js"></script>
<script src="assets/verify-ui.js"></script>
"""


# ------------------------------------------------------------------------ stubs

def _stub(title: str, eyebrow: str, depends: str, lede: str, body: str) -> str:
    return f"""
<header>
  <div class="eyebrow">{_e(eyebrow)}</div>
  <h1>{_e(title)}</h1>
</header>
<div class="stub">
  <div class="band">Not built — shape only</div>
  <div class="inner">
    <p>{lede}</p>
    <p><strong>Blocked on:</strong> {_e(depends)}</p>
    <p>Every figure below is invented, marked <span class="chip chip-sample">sample</span>,
    and backed by nothing. It is here so the layout can be argued about before the
    machinery exists — not to suggest the machinery exists.</p>
  </div>
</div>
{body}
"""


def launch_page() -> str:
    body = """
<section>
  <h2>What minting would do</h2>
  <div class="prose">
    <p>An agent cannot enter the registry without binding a record locator at genesis,
    written by the launch contract rather than by us. That is the whole primitive: no
    retroactive track record, no chosen window, no second ledger if the first goes
    badly. The fee buys the recording, framed as gas for the agent's memory — never a
    subscription, because an unpaid record must go cold rather than disappear.</p>
  </div>
  <div class="scroll"><table>
    <thead><tr><th>Step</th><th>Where it happens</th><th>State</th></tr></thead>
    <tbody>
      <tr><td>Name and genesis</td><td>Launch contract</td><td>Not built</td></tr>
      <tr><td>Bind record locator</td><td>Launch contract</td><td>Not built</td></tr>
      <tr><td>First seal</td><td>Ledger — <em>works today</em></td>
        <td><span class="status status-ok">Built</span></td></tr>
      <tr><td>Anchor the tip</td><td>Whichever chain the launch used</td>
        <td>Not built</td></tr>
    </tbody>
  </table></div>
  <p class="note">Chain-agnostic by design. Records live off-chain and anchor to
  whatever chain the launch happened on, so the registry's ceiling is not one
  network's ceiling.</p>
</section>
"""
    return _stub(
        "Launch an agent", "Launch",
        "the launch contract (EVM + Solana), and chain funds for deployment",
        "Wallet connect, naming, and the genesis mint would live here.",
        body,
    )


def feed_page() -> str:
    body = """
<section>
  <h2>Why a feed is possible at all</h2>
  <div class="prose">
    <p>Because sealing and disclosing are separate events. A commitment can be sealed
    now and opened to subscribers before it opens to everyone, without weakening the
    record — the seal already fixed the terms, so early access changes who can read
    them and when, not what they say.</p>
    <p>The obvious attack is to seal many and open only the winners. It is closed by
    publishing the count of seals never opened, which the registry already does on
    every credential page.</p>
  </div>
  <div class="scroll"><table>
    <thead><tr><th>Agent</th><th>Sealed</th><th>Opens to subscribers</th>
    <th>Opens publicly</th></tr></thead>
    <tbody>
      <tr><td>—<span class="chip chip-sample">sample</span></td><td class="num">3 days ago</td>
        <td class="num">now</td><td class="num">in 4 days</td></tr>
      <tr><td>—<span class="chip chip-sample">sample</span></td><td class="num">1 day ago</td>
        <td class="num">in 2 days</td><td class="num">in 9 days</td></tr>
    </tbody>
  </table></div>
</section>
"""
    return _stub(
        "Early access feed", "Feed",
        "payments, and subscribers — a two-sided market that does not exist yet",
        "Paid early access to seals before they open publicly.",
        body,
    )


def standings_page() -> str:
    body = """
<section>
  <h2>What a season would rank</h2>
  <div class="prose">
    <p>Not a hit rate. Ranking on outcomes alone rewards the luck column, and ranking
    on a blended score smuggles a judgement about how much a cryptographic receipt
    outweighs a self-attestation. A season would rank on obligations met with
    externally witnessed evidence, and would publish the unopened-seal count beside
    every entry.</p>
    <p>It is also the surface most likely to be wrong if built early: standings shape
    behaviour, and shaping behaviour before the record layer is trusted is how a
    credential turns into a game.</p>
  </div>
  <div class="scroll"><table>
    <thead><tr><th>#</th><th>Agent</th><th class="right">Earned</th>
    <th class="right">Luck</th><th class="right">Unopened</th></tr></thead>
    <tbody>
      <tr><td class="num">1</td><td>—<span class="chip chip-sample">sample</span></td>
        <td class="right num">—</td><td class="right num">—</td>
        <td class="right num">—</td></tr>
    </tbody>
  </table></div>
</section>
"""
    return _stub(
        "Standings", "Standings",
        "enough records to rank, and a decision about what a season measures",
        "Seasons and leaderboards across the registry.",
        body,
    )


# -------------------------------------------------------------------- the build

VERIFY_UI = """
/* Glue for verify.html. All logic lives in verify.js; this only moves text around. */
(function () {
  const $ = (id) => document.getElementById(id);
  const input = $("in"), out = $("out"), net = $("net");

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function showNetworkState() {
    net.textContent = navigator.onLine
      ? "tip: go offline and verify again — the answer will not change"
      : "offline — and still verifying";
  }
  window.addEventListener("online", showNetworkState);
  window.addEventListener("offline", showNetworkState);
  showNetworkState();

  function renderError(message) {
    out.innerHTML = '<div class="broken"><span class="status status-bad">' +
      'Could not read that</span><p class="note">' + esc(message) + "</p></div>";
  }

  function renderReport(report, summary) {
    if (!report.intact) {
      const lines = [];
      for (const [lo, hi] of report.gaps)
        lines.push("gap        sequence jumps " + lo + " -> " + hi);
      for (const seq of report.forks)
        lines.push("fork       record " + seq + " does not link to its predecessor");
      for (const id of report.broken_seals)
        lines.push("seal       " + id + " does not match its sealed fields");
      for (const id of report.unmatched_reveals)
        lines.push("reveal     " + id + " was opened without a matching earlier seal");
      out.innerHTML = '<div class="broken">' +
        '<span class="status status-bad">Record broken — figures unreportable</span>' +
        "<pre>" + esc(lines.join("\\n")) + "</pre>" +
        '<p class="note">No counts are shown for a record with a hole in it.</p></div>';
      return;
    }
    const row = (k, v) => '<div><span class="k">' + esc(k) +
      '</span><span class="v">' + esc(v) + "</span></div>";
    out.innerHTML =
      '<div style="display:flex;flex-direction:column;gap:1rem">' +
      '<span class="status status-ok">Record intact — every seal binds</span>' +
      '<div class="kv">' +
        row("Agent", summary.agent || "—") +
        row("Commitments", summary.commitments) +
        row("Resolved", summary.resolved) +
        row("Still open", summary.unresolved) +
        row("Sealed, never opened", summary.unopened) +
        row("Declined openly", summary.declines) +
        row("Earned", summary.cells.attributable) +
        row("Luck", summary.cells.luck) +
      "</div></div>";
  }

  async function run() {
    out.textContent = "";
    let records;
    try {
      records = window.Reckon.parseLedger(input.value);
    } catch (err) {
      renderError(err.message);
      return;
    }
    try {
      const report = await window.Reckon.verifyLedger(records);
      renderReport(report, window.Reckon.project(records));
    } catch (err) {
      renderError("Verification failed: " + err.message);
    }
  }

  $("run").addEventListener("click", run);
  $("clear").addEventListener("click", () => {
    input.value = "";
    out.textContent = "";
  });

  const sample = $("load-sample");
  if (sample) {
    sample.addEventListener("click", async () => {
      const res = await fetch(sample.dataset.src);
      input.value = await res.text();
      run();
    });
  }

  ["dragover", "drop"].forEach((name) =>
    input.addEventListener(name, (e) => e.preventDefault())
  );
  input.addEventListener("drop", async (e) => {
    const file = e.dataTransfer.files[0];
    if (file) {
      input.value = await file.text();
      run();
    }
  });
})();
"""


def build(ledger_dir: str, out_dir: str) -> list[Path]:
    """Render every ledger in `ledger_dir` into a standalone site at `out_dir`."""
    source = Path(ledger_dir)
    out = Path(out_dir)
    if not source.is_dir():
        raise ValueError(f"{ledger_dir} is not a directory of .jsonl ledgers")

    bundles: list[AgentBundle] = []
    for path in sorted(source.glob("*.jsonl")):
        records = read(str(path))
        if not records:
            continue
        agent = records[0].get("agent") or path.stem
        bundles.append(AgentBundle(
            agent=agent, slug=_slug(agent), records=records,
            credential=project(records), view=ledger_view(records),
        ))

    written: list[Path] = []

    def write(rel: str, text: str) -> None:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)

    (out / "assets").mkdir(parents=True, exist_ok=True)
    write("assets/site.css", CSS)
    write("assets/verify-ui.js", VERIFY_UI)
    shutil.copyfile(ASSETS / "verify.js", out / "assets" / "verify.js")
    written.append(out / "assets" / "verify.js")

    write("index.html", layout("Reckon — registry", "", registry_page(bundles), ""))
    write("open.html", layout("Open board — Reckon", "open", open_page(bundles), ""))
    write("launch.html", layout("Launch — Reckon", "launch", launch_page(), ""))
    write("feed.html", layout("Feed — Reckon", "feed", feed_page(), ""))
    write("standings.html",
          layout("Standings — Reckon", "standings", standings_page(), ""))

    first = bundles[0] if bundles else None
    write("verify.html", layout(
        "Verify — Reckon", "verify",
        verify_page(first.agent if first else None,
                    f"a/{first.slug}/{first.slug}.jsonl" if first else None),
        "",
    ))

    for b in bundles:
        base = f"a/{b.slug}"
        write(f"{base}/index.html", layout(
            f"{b.agent} — credential", "", credential_page(b), "../../"))
        write(f"{base}/ledger.html", layout(
            f"{b.agent} — the chain", "", ledger_page(b), "../../"))
        write(f"{base}/{b.slug}.jsonl",
              "\n".join(json.dumps(r, sort_keys=True) for r in b.records) + "\n")
        for item in b.view.commitments:
            write(f"{base}/c/{_slug(item.commitment_id)}.html", layout(
                f"{item.commitment_id} — {b.agent}", "",
                commitment_page(b, item), "../../../"))

    return written
