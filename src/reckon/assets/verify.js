/* Reckon ledger verifier — runs entirely in the browser.
 *
 * This file is the point of the whole design: a credential that only its issuer can
 * check is a claim, not a credential. Nothing here talks to a server. Open the page,
 * cut the network, paste a ledger, still get an answer.
 *
 * The one hard requirement is byte-identical canonicalisation with Python's
 * `json.dumps(value, sort_keys=True, separators=(",", ":"))`. Two differences bite:
 * Python escapes every non-ASCII character as \uXXXX with lowercase hex and JS does
 * not, and Python sorts keys by code point while JS sorts by UTF-16 code unit. Both
 * are handled below, and `tests/test_canonical_parity.py` runs this file under node
 * against the Python implementation to prove it.
 */

const GENESIS_HASH = "sha256:genesis";

const EVIDENCE_CLASSES = ["A", "B", "C", "D"];

/* --- canonicalisation ---------------------------------------------------- */

/** Compare two strings by Unicode code point, the way Python's sorted() does. */
function byCodePoint(a, b) {
  const x = Array.from(a).map((c) => c.codePointAt(0));
  const y = Array.from(b).map((c) => c.codePointAt(0));
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    if (x[i] !== y[i]) return x[i] - y[i];
  }
  return x.length - y.length;
}

function sortDeep(value) {
  if (Array.isArray(value)) return value.map(sortDeep);
  if (value !== null && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort(byCodePoint)) {
      out[key] = sortDeep(value[key]);
    }
    return out;
  }
  return value;
}

/** Escape every character above ASCII, matching Python's ensure_ascii=True. */
// Built from a string so the source of this file stays pure ASCII; a literal
// character class here is the same set but silently unreadable in a diff.
const NON_ASCII = new RegExp("[\\u0080-\\uFFFF]", "g");

function escapeNonAscii(text) {
  return text.replace(NON_ASCII, (ch) =>
    "\\u" + ch.charCodeAt(0).toString(16).padStart(4, "0")
  );
}

function canonical(value) {
  return escapeNonAscii(JSON.stringify(sortDeep(value)));
}

async function digest(value) {
  const bytes = new TextEncoder().encode(canonical(value));
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return "sha256:" + hex;
}

/* --- the seal ------------------------------------------------------------ */

/** Rebuild the sealed payload exactly as Commitment._sealed_payload does. */
function sealedPayload(record) {
  return {
    commitment_id: record.commitment_id,
    objective: record.objective,
    obligation: {
      statement: record.obligation.statement,
      evidence_class: record.obligation.evidence_class,
      evidence_source: record.obligation.evidence_source,
    },
    obligation_criteria: record.obligation_criteria,
    outcome_criteria: record.outcome_criteria,
    horizon: record.horizon,
    sources: [...record.sources].sort(byCodePoint),
  };
}

/* --- verification -------------------------------------------------------- */

/** Mirror of reckon.integrity.verify_ledger. Same order, same findings. */
async function verifyLedger(records) {
  const gaps = [];
  const forks = [];
  const brokenSeals = [];
  const unmatchedReveals = [];

  let expectedPrev = GENESIS_HASH;
  let previousSeq = null;
  const pending = [];

  for (const record of records) {
    const seq = record.seq;
    const kind = record.kind;

    if (previousSeq !== null && seq !== previousSeq + 1) {
      gaps.push([previousSeq, seq]);
    }
    if (record.prev_hash !== expectedPrev) {
      forks.push(seq);
    }

    if (kind === "sealed_commitment") {
      pending.push(record.seal);
    } else if (kind === "commitment" || kind === "reveal") {
      const recomputed = await digest(sealedPayload(record));
      if (recomputed !== record.seal) brokenSeals.push(record.commitment_id);
      if (kind === "reveal") {
        const at = pending.indexOf(record.seal);
        if (at === -1) unmatchedReveals.push(record.commitment_id);
        else pending.splice(at, 1);
      }
    }

    previousSeq = seq;
    expectedPrev = await digest(record);
  }

  const intact =
    gaps.length === 0 &&
    forks.length === 0 &&
    brokenSeals.length === 0 &&
    unmatchedReveals.length === 0;

  return { intact, gaps, forks, broken_seals: brokenSeals, unmatched_reveals: unmatchedReveals };
}

/** Mirror of reckon.credential.project — counts and classes, never a rate. */
function project(records) {
  const cells = {
    attributable: 0,
    competent_unsuccessful: 0,
    luck: 0,
    failure: 0,
    indeterminate: 0,
  };
  const evidenceMix = { A: 0, B: 0, C: 0, D: 0 };
  let commitments = 0, declines = 0, sealed = 0, revealed = 0, resolved = 0;

  for (const record of records) {
    const kind = record.kind;
    if (kind === "commitment" || kind === "reveal") {
      commitments += 1;
      evidenceMix[record.obligation.evidence_class] += 1;
      if (kind === "reveal") revealed += 1;
    } else if (kind === "sealed_commitment") {
      sealed += 1;
    } else if (kind === "decline") {
      declines += 1;
    } else if (kind === "resolution") {
      resolved += 1;
      cells[record.cell] += 1;
    }
  }

  return {
    agent: records.length ? records[0].agent : "",
    commitments,
    declines,
    sealed,
    revealed,
    unopened: sealed - revealed,
    resolved,
    unresolved: commitments - resolved,
    cells,
    evidence_mix: evidenceMix,
  };
}

function parseLedger(text) {
  const records = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    try {
      records.push(JSON.parse(line));
    } catch (err) {
      throw new Error(`Line ${i + 1} is not valid JSON, so the record cannot be read.`);
    }
  }
  if (!records.length) throw new Error("No records found. A ledger is one JSON object per line.");
  for (const [n, record] of records.entries()) {
    for (const key of ["seq", "prev_hash"]) {
      if (record[key] === undefined) {
        throw new Error(`Record ${n + 1} has no ${key}, so it is not a Reckon ledger.`);
      }
    }
  }
  return records;
}

/* --- exports for both worlds -------------------------------------------- */

const API = { canonical, digest, verifyLedger, project, parseLedger, sealedPayload, byCodePoint };

if (typeof module !== "undefined" && module.exports) {
  module.exports = API;          // node, for the parity test
} else if (typeof window !== "undefined") {
  window.Reckon = API;           // browser
}
