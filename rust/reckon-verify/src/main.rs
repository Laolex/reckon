//! `reckon-verify <ledger.jsonl>` — check a ledger without trusting its writer.
//!
//! Exit codes are the interface: 0 intact, 1 findings, 2 the file could not be read
//! or parsed. The third is separate on purpose — "I could not check this" and "this
//! is broken" are different claims, and collapsing them would make the tool assert
//! something it does not know.

use std::process::ExitCode;

use reckon_verify::{verify_ledger, IntegrityReport};
use serde_json::Value;

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let Some(path) = args.next() else {
        eprintln!("usage: reckon-verify <ledger.jsonl>");
        return ExitCode::from(2);
    };

    let text = match std::fs::read_to_string(&path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("cannot read {path}: {e}");
            return ExitCode::from(2);
        }
    };

    let mut records: Vec<Value> = Vec::new();
    for (i, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        match serde_json::from_str(line) {
            Ok(v) => records.push(v),
            Err(e) => {
                eprintln!("{path}:{}: not valid JSON: {e}", i + 1);
                return ExitCode::from(2);
            }
        }
    }

    let report: IntegrityReport = verify_ledger(&records);
    println!("{}", report.render());
    if report.intact() {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}
