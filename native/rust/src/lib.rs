//! Latency-sensitive helpers. Each function has an identical Python fallback in
//! bangzen_prime/native/rust_bridge.py. Build with `maturin develop` from native/rust.
//! This crate performs no network I/O and no signing.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

const BPS_SCALE: u64 = 10_000;

/// Minimum acceptable output after slippage: out * (10000 - bps) / 10000, rounded down.
#[pyfunction]
fn min_out_amount(out_amount: u64, slippage_bps: u64) -> PyResult<u64> {
    if slippage_bps > BPS_SCALE {
        return Err(PyValueError::new_err("slippage out of range"));
    }
    out_amount
        .checked_mul(BPS_SCALE - slippage_bps)
        .map(|v| v / BPS_SCALE)
        .ok_or_else(|| PyValueError::new_err("overflow"))
}

/// Bundle size is 1 to 5 transactions and the tip must not exceed the cap.
#[pyfunction]
fn bundle_within_limits(num_txs: u64, tip_lamports: u64, cap_lamports: u64) -> bool {
    (1..=5).contains(&num_txs) && tip_lamports <= cap_lamports
}

/// Escapes the three characters Telegram HTML requires. Matches html.escape(quote=False).
#[pyfunction]
fn html_escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

#[pymodule]
fn bangzen_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(min_out_amount, m)?)?;
    m.add_function(wrap_pyfunction!(bundle_within_limits, m)?)?;
    m.add_function(wrap_pyfunction!(html_escape, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn min_out_amount_calculates_slippage_correctly() {
        assert_eq!(min_out_amount(10_000, 100).unwrap(), 9_900);
        assert_eq!(min_out_amount(10_000, 0).unwrap(), 10_000);
        assert_eq!(min_out_amount(10_000, 10_000).unwrap(), 0);
    }

    #[test]
    fn min_out_amount_rejects_slippage_above_limit() {
        assert!(min_out_amount(10_000, 10_001).is_err());
    }

    #[test]
    fn min_out_amount_rejects_overflow() {
        assert!(min_out_amount(u64::MAX, 1).is_err());
    }

    #[test]
    fn bundle_within_limits_accepts_valid_boundaries() {
        assert!(bundle_within_limits(1, 100, 100));
        assert!(bundle_within_limits(5, 100, 100));
        assert!(bundle_within_limits(3, 0, 100));
    }

    #[test]
    fn bundle_within_limits_rejects_invalid_transaction_counts() {
        assert!(!bundle_within_limits(0, 0, 100));
        assert!(!bundle_within_limits(6, 0, 100));
    }

    #[test]
    fn bundle_within_limits_rejects_tip_above_cap() {
        assert!(!bundle_within_limits(1, 101, 100));
    }

    #[test]
    fn html_escape_handles_required_characters() {
        assert_eq!(html_escape("&<>"), "&amp;&lt;&gt;");
    }

    #[test]
    fn html_escape_handles_multiple_ampersands_safely() {
        assert_eq!(html_escape("A & B && C"), "A &amp; B &amp;&amp; C");
    }

    #[test]
    fn html_escape_preserves_unrelated_text() {
        assert_eq!(html_escape("BANGZEN PRIME 2026"), "BANGZEN PRIME 2026");
    }
}
