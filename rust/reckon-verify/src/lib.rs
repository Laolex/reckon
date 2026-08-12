//! An independent verifier for Reckon ledgers.
//!
//! The value of a third implementation is not speed. It is that a record verified
//! by code that shares nothing with the writer — not a library, not a language, not
//! an author's assumptions — is verified by something that cannot inherit the
//! writer's mistake. Python writes, JavaScript checks in the browser, Rust checks
//! offline. Agreement across three is evidence; agreement with yourself is not.

pub mod canonical;
pub mod ledger;

pub use canonical::{canonical, digest};
pub use ledger::{verify_ledger, IntegrityReport, GENESIS_HASH};
