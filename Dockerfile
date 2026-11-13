# ==========================================
# STAGE 1: Builder (Kompilasi Rust & Python)
# ==========================================
FROM python:3.11-slim-bookworm AS builder

# Install dependensi sistem untuk kompilasi Rust
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Rust Toolchain
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Maturin (alat untuk build wheel Rust -> Python)
RUN pip install --no-cache-dir maturin

WORKDIR /app

# Copy file proyek
COPY . .

# Build Native Rust Extension (sesuaikan path jika Cargo.toml ada di folder 'native/')
WORKDIR /app/native/rust
RUN maturin build --release -o /app/dist

# ==========================================
# STAGE 2: Runtime (Image Final yang Ringan)
# ==========================================
FROM python:3.11-slim-bookworm

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BANGZEN_LIVE_TRADING=false \
    BANGZEN_BROADCAST_ENABLED=false

# Copy the full project so pyproject.toml's readme and the package exist at install time.
# .dockerignore keeps .env, data/, and build output out of the image.
COPY . ./

RUN pip install --no-cache-dir .

# Copy hasil build Rust (Wheel) dari Stage 1 dan install
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

RUN useradd --create-home --uid 10001 bangzen \
 && mkdir -p /app/data /app/logs \
 && chown -R bangzen:bangzen /app/data /app/logs
USER bangzen

# Default command (bisa dioverride di docker-compose)
CMD ["python", "-m", "bangzen_prime", "status"]
