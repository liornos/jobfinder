.PHONY: venv install lint format fmt type test test-cov ci

VENV ?= .venv
PY ?= py
VENV_PY := $(VENV)/Scripts/python.exe

$(VENV_PY):
	$(PY) -m venv $(VENV)
	$(VENV_PY) -m pip install --upgrade pip

venv: $(VENV_PY)

install: $(VENV_PY)
	$(VENV_PY) -m pip install -e ".[dev]"

lint: $(VENV_PY)
	$(VENV_PY) -m ruff check .

format: $(VENV_PY)
	$(VENV_PY) -m ruff format --check .

fmt: $(VENV_PY)
	$(VENV_PY) -m ruff format .

type: $(VENV_PY)
	$(VENV_PY) -m mypy jobfinder tests

test: $(VENV_PY)
	$(VENV_PY) -m pytest -q

test-cov: $(VENV_PY)
	$(VENV_PY) -m pytest -q --cov=jobfinder --cov-report=term-missing

ci: lint format type test
