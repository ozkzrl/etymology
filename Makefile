.PHONY: help install test test-live lint fix coverage clean serve web

help:
	@echo "install     - .venv oluştur ve bağımlılıkları kur"
	@echo "test        - Ağsız test paketi"
	@echo "test-live   - Canlı kaynak testleri (ağ gerektirir)"
	@echo "lint        - ruff denetimi"
	@echo "fix         - ruff otomatik düzeltme"
	@echo "coverage    - Kapsam raporu (%90 eşiği)"
	@echo "serve       - REST API sunucusu"
	@echo "web         - Web panelini yayınla (localhost:3000)"
	@echo "clean       - Önbellek ve geçici dosyaları sil"

install:
	python3 -m venv .venv || uv venv .venv
	.venv/bin/python -m pip install -e ".[dev,phon,pdf]" || \
		uv pip install --python .venv/bin/python -e ".[dev,phon,pdf]"

test:
	.venv/bin/pytest -q

test-live:
	ETY_LIVE=1 .venv/bin/pytest engine/tests/live -v

lint:
	.venv/bin/ruff check engine/ scripts/

fix:
	.venv/bin/ruff check engine/ scripts/ --fix

coverage:
	.venv/bin/pytest --cov=engine --cov-report=term-missing --cov-fail-under=90

serve:
	.venv/bin/python -m engine.server

web:
	cd web && npx serve -l 3000 .

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
