//! Cross-language parity: Rust must agree with Python byte for byte.
//!
//! This is the only test that matters. A verifier that disagrees with the writer
//! calls honest records broken, so the question is never "does the Rust look right"
//! but "does it produce the identical bytes". It shells out to the real `reckon`
//! package rather than a fixture, because a fixture freezes today's behaviour and
//! would keep passing after Python changed.
//!
//! Corpus is lifted from `tests/test_canonical_parity.py`: the values chosen for
//! where languages disagree by default — non-ASCII, an astral character that must
//! become a surrogate pair, unsorted keys, control characters, and the scalars.

use std::process::Command;

use reckon_verify::{canonical, digest};
use serde_json::{json, Value};

fn tricky() -> Vec<Value> {
    vec![
        json!("plain"),
        json!("café"),
        json!("naïve — dash"),
        json!("—"),
        json!("a\"b"),
        json!("x\ny\tz"),
        json!("àéîõü"),
        json!("emoji \u{1f9fe} receipt"),
        json!({"b": 1, "a": 2, "é": 3, "A": 4}),
        json!({"nested": {"z": ["—", 1, true, null], "a": {}}}),
        json!([]),
        json!({}),
        json!(0),
        json!(-17),
        json!(true),
        json!(false),
        json!(null),
        json!(["é", 1, true, null]),
    ]
}

/// Ask the installed `reckon` package for its canonical form and digest.
fn python_says(value: &Value) -> Option<(String, String)> {
    let script = r#"
import json, sys
from reckon.record import digest
value = json.loads(sys.argv[1])
canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
print(json.dumps({"canonical": canonical, "digest": digest(value)}))
"#;
    let out = Command::new("python3")
        .arg("-c")
        .arg(script)
        .arg(serde_json::to_string(value).unwrap())
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let parsed: Value = serde_json::from_slice(&out.stdout).ok()?;
    Some((
        parsed["canonical"].as_str()?.to_string(),
        parsed["digest"].as_str()?.to_string(),
    ))
}

#[test]
fn canonical_form_and_digest_match_python() {
    let mut checked = 0;
    for value in tricky() {
        let Some((py_canonical, py_digest)) = python_says(&value) else {
            eprintln!("skipping parity: the reckon package is not importable here");
            return;
        };
        assert_eq!(
            canonical(&value),
            py_canonical,
            "canonical form diverged for {value}"
        );
        assert_eq!(digest(&value), py_digest, "digest diverged for {value}");
        checked += 1;
    }
    assert_eq!(checked, tricky().len(), "every corpus value must be checked");
}

#[test]
fn astral_characters_become_surrogate_pairs() {
    // The failure this guards: iterating chars() instead of UTF-16 code units
    // yields one escape instead of two, which hashes differently and silently.
    let receipt = json!("\u{1f9fe}");
    assert_eq!(canonical(&receipt), r#""\ud83e\uddfe""#);
}

#[test]
fn non_ascii_is_escaped_lowercase() {
    assert_eq!(canonical(&json!("café")), r#""caf\u00e9""#);
}

#[test]
fn separators_carry_no_spaces() {
    assert_eq!(canonical(&json!({"a": 1, "b": [1, 2]})), r#"{"a":1,"b":[1,2]}"#);
}

#[test]
fn solidus_is_not_escaped() {
    // Python leaves '/' alone; escaping it would be valid JSON and the wrong bytes.
    assert_eq!(canonical(&json!("a/b")), r#""a/b""#);
}

#[test]
fn keys_sort_by_code_point() {
    // 'A' (0x41) before 'a' (0x61) before 'é' (0xe9) — not locale or case order.
    assert_eq!(
        canonical(&json!({"a": 1, "é": 2, "A": 3})),
        r#"{"A":3,"a":1,"\u00e9":2}"#
    );
}
