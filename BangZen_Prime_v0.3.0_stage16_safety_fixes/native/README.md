# Rust core (optional)

`native/rust` builds the `bangzen_native` module with PyO3 and maturin:

    pip install maturin
    cd native/rust && maturin develop --release

Without it, `bangzen_prime/native/rust_bridge.py` uses the Python implementations. This build
environment had no Rust toolchain, so the crate was NOT compiled or tested here. Its behaviour is
asserted equal to the Python path by tests that run only when the module imports.
