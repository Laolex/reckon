//! Ledger verification. Mirror of `reckon.integrity.verify_ledger`, finding for finding.
//!
//! Two detectors, not one, and they catch different lies. `prev_hash` proves nothing
//! was edited. `seq` proves nothing was *removed* — a chain that has had a whole
//! record excised still links perfectly, because the remaining records were never
//! touched. A hash chain alone cannot see that.
//!
//! Output names the specific evidence that failed. There is no score, and no
//! "probably fine": either a finding is present or the record is intact.

use serde_json::Value;

use crate::canonical::digest;

pub const GENESIS_HASH: &str = "sha256:genesis";

#[derive(Debug, Default, PartialEq, Eq)]
pub struct IntegrityReport {
    pub gaps: Vec<(i64, i64)>,
    pub forks: Vec<i64>,
    pub broken_seals: Vec<String>,
    pub unmatched_reveals: Vec<String>,
}

impl IntegrityReport {
    pub fn intact(&self) -> bool {
        self.gaps.is_empty()
            && self.forks.is_empty()
            && self.broken_seals.is_empty()
            && self.unmatched_reveals.is_empty()
    }

    /// Same wording as the Python renderer, so a reader cannot tell which
    /// implementation produced a report without being told.
    pub fn render(&self) -> String {
        if self.intact() {
            return "Record intact: no gaps, no forks, every seal binds.".to_string();
        }
        let mut lines = Vec::new();
        for (lo, hi) in &self.gaps {
            lines.push(format!("gap        sequence jumps {lo} -> {hi}"));
        }
        for seq in &self.forks {
            lines.push(format!(
                "fork       record {seq} does not link to its predecessor"
            ));
        }
        for cid in &self.broken_seals {
            lines.push(format!("seal       {cid} does not match its sealed fields"));
        }
        for cid in &self.unmatched_reveals {
            lines.push(format!(
                "reveal     {cid} was opened without a matching earlier seal"
            ));
        }
        lines.join("\n")
    }
}

/// Rebuild the sealed payload exactly as `Commitment._sealed_payload` does.
///
/// Returns `None` when a field the seal depends on is absent: a record that cannot
/// be re-sealed is not the same thing as a record whose seal is wrong, and calling
/// it "broken" would be a claim this function has no evidence for.
fn sealed_payload(record: &Value) -> Option<Value> {
    let obligation = record.get("obligation")?;
    let mut sources: Vec<String> = record
        .get("sources")?
        .as_array()?
        .iter()
        .map(|s| s.as_str().unwrap_or_default().to_string())
        .collect();
    sources.sort(); // bytewise over UTF-8 == code point order; see canonical.rs

    Some(serde_json::json!({
        "commitment_id": record.get("commitment_id")?,
        "objective": record.get("objective")?,
        "obligation": {
            "statement": obligation.get("statement")?,
            "evidence_class": obligation.get("evidence_class")?,
            "evidence_source": obligation.get("evidence_source")?,
        },
        "obligation_criteria": record.get("obligation_criteria")?,
        "outcome_criteria": record.get("outcome_criteria")?,
        "horizon": record.get("horizon")?,
        "sources": sources,
    }))
}

pub fn verify_ledger(records: &[Value]) -> IntegrityReport {
    let mut report = IntegrityReport::default();
    let mut expected_prev = GENESIS_HASH.to_string();
    let mut previous_seq: Option<i64> = None;
    // Seals written and not yet opened. A reveal consumes one, so opening the same
    // seal twice — or opening one never written — has nothing to consume.
    let mut pending: Vec<String> = Vec::new();

    for record in records {
        let seq = record.get("seq").and_then(Value::as_i64).unwrap_or_default();
        let kind = record.get("kind").and_then(Value::as_str).unwrap_or_default();

        if let Some(prev) = previous_seq {
            if seq != prev + 1 {
                report.gaps.push((prev, seq));
            }
        }
        if record.get("prev_hash").and_then(Value::as_str) != Some(expected_prev.as_str()) {
            report.forks.push(seq);
        }

        let seal = record.get("seal").and_then(Value::as_str).unwrap_or_default();
        match kind {
            "sealed_commitment" => pending.push(seal.to_string()),
            "commitment" | "reveal" => {
                if let Some(payload) = sealed_payload(record) {
                    if digest(&payload) != seal {
                        report.broken_seals.push(commitment_id(record));
                    }
                }
                if kind == "reveal" {
                    match pending.iter().position(|s| s == seal) {
                        Some(at) => {
                            pending.remove(at);
                        }
                        None => report.unmatched_reveals.push(commitment_id(record)),
                    }
                }
            }
            _ => {}
        }

        previous_seq = Some(seq);
        expected_prev = digest(record);
    }

    report
}

fn commitment_id(record: &Value) -> String {
    record
        .get("commitment_id")
        .and_then(Value::as_str)
        .unwrap_or("<no commitment_id>")
        .to_string()
}
