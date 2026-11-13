PY ?= python3
.DEFAULT_GOAL := help

.PHONY: help setup format lint typecheck check compile test test-unit test-integration test-e2e coverage build verify-wheel demo soak clean

help: ## Tampilkan daftar perintah yang tersedia
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Instalasi awal untuk development
	$(PY) -m pip install --upgrade pip setuptools wheel
	$(PY) -m pip install -e ".[dev]"

format: ## Rapikan kode secara otomatis (Black)
	$(PY) -m black .

lint: ## Cek error dan import yang tidak terpakai (Ruff)
	$(PY) -m ruff check . --fix

typecheck: ## Cek tipe data (Mypy)
	$(PY) -m mypy bangzen_prime

compile: ## Cek syntax error tanpa menjalankan kode
	$(PY) -m compileall -q bangzen_prime tests scripts

test: ## Jalankan SEMUA test (380+ test)
	$(PY) scripts/run_tests.py

test-unit: ## Jalankan hanya unit test
	$(PY) -m unittest discover -s tests/unit -t . -p "test_*.py"

test-integration: ## Jalankan hanya integration test
	$(PY) -m unittest discover -s tests/integration -t . -p "test_*.py"

test-e2e: ## Jalankan hanya end-to-end test
	$(PY) -m unittest discover -s tests/e2e -t . -p "test_*.py"

coverage: ## Cek seberapa banyak kode yang di-test
	$(PY) scripts/coverage_lite.py

build: ## Bangun paket wheel (dengan pengaman setuptools)
	rm -rf dist build
	$(PY) -m venv .build-venv
	.build-venv/bin/python -m pip install --upgrade pip setuptools wheel
	.build-venv/bin/python -m pip wheel . --no-deps -w dist
	rm -rf .build-venv

verify-wheel: build ## Uji coba paket wheel di ruang bersih
	rm -rf .verify-venv
	$(PY) -m venv .verify-venv
	.verify-venv/bin/pip install -q --no-index --no-deps dist/*.whl
	.verify-venv/bin/bangzen-prime --help > /dev/null
	.verify-venv/bin/bangzen-prime demo --scans 25 > /dev/null
	rm -rf .verify-venv

check: format lint typecheck compile test ## Jalankan semua pengecekan sebelum push
	@echo "✅ SEMUA PENGECEKAN LULUS! SIAP PUSH KE GITHUB."

demo: ## Simulasi bot (scan offline)
	$(PY) -m bangzen_prime demo

soak: ## Uji ketahanan bot (200 siklus)
	$(PY) -m bangzen_prime soak --cycles 200 --seed 7

clean: ## Hapus semua file sampah (build, cache, dll)
	rm -rf dist build *.egg-info .verify-venv .mypy_cache .ruff_cache reports/*.xml
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
