.PHONY: venv db seed api web test fmt

venv:
	uv venv --python 3.12 .venv
	. .venv/bin/activate && uv pip install -e api

db:
	.venv/bin/python scripts/dev_db.py

seed:
	cd api && ../.venv/bin/python -m app.seed

api:
	cd api && ../.venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd web && pnpm dev

test:
	cd api && ../.venv/bin/pytest -q

fmt:
	cd api && ../.venv/bin/ruff format app tests
