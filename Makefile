UV ?= uv

.PHONY: setup lint format-check type test check audit demo

setup:
	$(UV) sync --locked --all-extras

lint:
	$(UV) run --locked --extra dev ruff check .

format-check:
	$(UV) run --locked --extra dev ruff format --check .

type:
	$(UV) run --locked --extra dev mypy src

test:
	$(UV) run --locked --extra dev pytest

check: lint format-check type test

audit:
	$(UV) run --locked --extra dev pip-audit

demo:
	$(UV) run actionlineage demo run --output-dir build/actionlineage-demo
