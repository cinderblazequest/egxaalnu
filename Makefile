.PHONY: install dev lint format test bot dashboard pdf metronome clean help

PYTHON ?= python3
VENV    = .venv
PIP     = $(VENV)/bin/pip
PY      = $(VENV)/bin/python

help:
	@echo "СПАС — целевые команды:"
	@echo "  make install     — установить prod-зависимости в .venv"
	@echo "  make dev         — установить dev-зависимости (тесты, lint, PDF)"
	@echo "  make lint        — ruff check"
	@echo "  make format      — ruff format"
	@echo "  make test        — pytest"
	@echo "  make bot         — запустить бота локально (нужен .env с BOT_TOKEN)"
	@echo "  make dashboard   — запустить Streamlit-дашборд"
	@echo "  make metronome   — сгенерировать audio/metronome_*.mp3"
	@echo "  make pdf         — собрать docs/build/*.pdf"
	@echo "  make clean       — удалить артефакты"

$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip wheel

install: $(VENV)/bin/python
	$(PIP) install -r requirements.txt

dev: $(VENV)/bin/python
	$(PIP) install -r requirements-dev.txt

lint:
	$(VENV)/bin/ruff check .

format:
	$(VENV)/bin/ruff format .

test:
	$(VENV)/bin/pytest -q

bot:
	$(PY) -m bot

dashboard:
	$(VENV)/bin/streamlit run dashboard.py

metronome:
	$(PY) tools/generate_metronome.py

pdf:
	$(PY) tools/generate_infographic_pdf.py
	$(PY) tools/generate_methodology_pdf.py

clean:
	rm -rf $(VENV) build dist .pytest_cache .ruff_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
