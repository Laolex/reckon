"""The public credential page. Standard library only.

When the record is broken the page prints no figures at all. A number beside a
warning is still a number, and readers keep the number.
"""

from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer

from .credential import Credential, project
from .ledger import read

CELL_LABELS = {
    "attributable": "Did the work, got the result",
    "competent_unsuccessful": "Did the work, result did not come",
    "luck": "Luck — result came, work was not done",
    "failure": "Work not done, result not achieved",
    "indeterminate": "Could not be settled",
}

_CSS = """
body{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;max-width:46rem;
margin:3rem auto;padding:0 1.25rem;line-height:1.55;background:#faf8f4;color:#1a1712}
h1{font-size:1.4rem;margin:0 0 .25rem}
.sub{color:#6b655c;font-size:.85rem;margin-bottom:2rem}
.bad{color:#a03a26}.good{color:#2e6b52}
table{border-collapse:collapse;width:100%;margin:1rem 0 2rem}
td,th{text-align:left;padding:.45rem .5rem;border-bottom:1px solid #e3ded4;
font-variant-numeric:tabular-nums}
th{font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:#8c857a}
pre{overflow-x:auto;background:#f2eee6;padding:.75rem;border-radius:3px}
@media(prefers-color-scheme:dark){body{background:#14120e;color:#f0ebe1}
td,th{border-color:#302b23}.sub,th{color:#9a9184}
pre{background:#1e1a15}
.bad{color:#d9694e}.good{color:#5fa383}}
"""


def _rows(pairs: list[tuple[str, object]]) -> str:
    return "".join(
        f"<tr><td>{escape(str(k))}</td><td>{escape(str(v))}</td></tr>" for k, v in pairs
    )


def render(credential: Credential) -> str:
    agent = escape(credential.agent)
    integrity = credential.integrity

    if not integrity.intact:
        detail = escape(integrity.render())
        body = (
            '<p class="bad"><strong>Record broken — figures unreportable.</strong></p>'
            f"<pre>{detail}</pre>"
            "<p>Any hit rate computed over a record with a hole in it would be a guess. "
            "None is shown.</p>"
        )
    else:
        cells = _rows([(CELL_LABELS[name], count)
                       for name, count in credential.cells.items()])
        evidence = _rows([(f"Class {name}", count)
                          for name, count in credential.evidence_mix.items()])
        counts = _rows([
            ("Commitments sealed", credential.commitments),
            ("Declined openly", credential.declines),
            ("Resolved", credential.resolved),
            ("Still open", credential.unresolved),
            ("Completeness", credential.completeness),
        ])
        body = (
            '<p class="good">Record intact since genesis.</p>'
            f"<table><tr><th>Activity</th><th>Count</th></tr>{counts}</table>"
            "<table><tr><th>Obligation and outcome</th><th>Count</th></tr>"
            f"{cells}</table>"
            "<table><tr><th>Evidence class</th><th>Count</th></tr>"
            f"{evidence}</table>"
        )

    genesis = escape(str(credential.genesis or "—"))
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<title>{agent} — credential</title>"
        f"<style>{_CSS}</style>"
        f"<h1>{agent}</h1>"
        f"<p class='sub'>Record begins {genesis}. Every figure is computed over the "
        "whole record; there is no date filter.</p>"
        f"{body}"
    )


def serve(ledger_path: str, port: int = 8799) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            html = render(project(read(ledger_path))).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *args) -> None:
            pass

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
