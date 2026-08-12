//! Canonicalisation, byte-identical with Python's `reckon.record.digest`.
//!
//! A verifier that disagrees with the writer is worse than no verifier: it calls
//! honest records broken. So this is not "a reasonable JSON serialisation" — it is
//! a deliberate reimplementation of exactly what
//! `json.dumps(value, sort_keys=True, separators=(",", ":"))` produces, including
//! the parts of that behaviour nobody would choose on purpose.
//!
//! Three places where the obvious Rust implementation is wrong:
//!
//! 1. `serde_json::to_string` does not escape non-ASCII. Python's `ensure_ascii`
//!    defaults to true, so `café` must serialise as `café`. Every character
//!    above U+007F is escaped, lowercase hex, four digits.
//!
//! 2. Escaping is defined over **UTF-16 code units**, not Unicode scalars. Python
//!    emits a surrogate pair for astral characters, so U+1F9FE becomes
//!    `🧾` and not `ᾟe`. Iterating `chars()` would silently produce
//!    a different, shorter string that hashes differently.
//!
//! 3. Keys sort by Unicode code point. Rust's `str` ordering is bytewise over
//!    UTF-8, which is *the same order* — UTF-8 was designed so byte order equals
//!    code point order — so `sort()` is correct here. It is spelled out because
//!    the equivalence is load-bearing and not obvious to a future reader.

use serde_json::Value;
use sha2::{Digest, Sha256};

/// Serialise `value` exactly as Python's canonical form.
pub fn canonical(value: &Value) -> String {
    let mut out = String::new();
    write_value(value, &mut out);
    out
}

/// `sha256:` + hex digest of the canonical form. Mirrors `reckon.record.digest`.
pub fn digest(value: &Value) -> String {
    let mut hasher = Sha256::new();
    hasher.update(canonical(value).as_bytes());
    format!("sha256:{:x}", hasher.finalize())
}

fn write_value(value: &Value, out: &mut String) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Number(n) => out.push_str(&n.to_string()),
        Value::String(s) => write_string(s, out),
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_value(item, out);
            }
            out.push(']');
        }
        Value::Object(map) => {
            // serde_json's Map is a BTreeMap unless `preserve_order` is enabled, so
            // this is already sorted — collected and sorted explicitly anyway so the
            // guarantee survives a future feature flag rather than depending on one.
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            out.push('{');
            for (i, key) in keys.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_string(key, out);
                out.push(':');
                write_value(&map[key.as_str()], out);
            }
            out.push('}');
        }
    }
}

/// Write a JSON string literal the way Python's encoder does.
fn write_string(s: &str, out: &mut String) {
    out.push('"');
    // encode_utf16 is the point: escaping is defined per UTF-16 code unit, so an
    // astral character arrives here as its surrogate pair and is escaped as two
    // units, matching Python. chars() would give one scalar and the wrong bytes.
    for unit in s.encode_utf16() {
        match unit {
            0x22 => out.push_str("\\\""),
            0x5C => out.push_str("\\\\"),
            0x08 => out.push_str("\\b"),
            0x0C => out.push_str("\\f"),
            0x0A => out.push_str("\\n"),
            0x0D => out.push_str("\\r"),
            0x09 => out.push_str("\\t"),
            // Control characters below space, and everything above ASCII.
            // Python does not escape '/', so it is deliberately absent here.
            u if u < 0x20 || u > 0x7E => out.push_str(&format!("\\u{:04x}", u)),
            u => out.push(u as u8 as char),
        }
    }
    out.push('"');
}
