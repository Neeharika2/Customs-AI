.PHONY: venv db seed api web build test e2e fmt

venv:
	cd api && uv sync

db:
	cd api && uv run python ../scripts/dev_db.py

seed:
	cd api && uv run python ../seed/generate.py
	cd api && uv run python ../seed/seed_demo.py

api:
	cd api && uv run uvicorn app.main:app --reload --port 8000

web:
	cd web && pnpm dev

build:
	cd web && pnpm build
	rm -rf api/app/static
	mkdir -p api/app/static
	cp -r web/dist/. api/app/static/

test:
	cd api && uv run pytest -q

e2e:
	cd web && pnpm test:e2e

fmt:
	cd api && uv run ruff format app tests
