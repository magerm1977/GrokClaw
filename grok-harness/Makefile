.PHONY: setup test test-coverage lint

setup:
	python -m venv .venv
	.venv\Scripts\activate 2>nul || .venv/bin/activate
	pip install -e ".[dev]" 2>nul || pip install -e ".[dev]"

install:
	pip install -r requirements/dev.txt

test:
	pytest tests/ -v

test-coverage:
	pytest tests/ --cov=src/grok_harness --cov-report=term-missing

lint:
	ruff check src/ tests/
	black --check src/ tests/
