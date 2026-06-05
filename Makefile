.PHONY: install install-dev dev run test test-cov format lint typecheck check \
        autoflake isort black flake8 mypy \
        migrate migrate-create migrate-downgrade docker-build docker-run

LINT_DIRS := dating tests

# ── Dependencies ──────────────────────────────────────────────────────────
install:
	pip install -r requirements/prod.txt

install-dev:
	pip install -r requirements/ci.txt
	pip install -e .

# ── Run ───────────────────────────────────────────────────────────────────
dev:
	python main.py

run:
	uvicorn main:create_app --factory --host 0.0.0.0 --port 8010

# ── Database migrations ───────────────────────────────────────────────────
migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(msg)"

migrate-downgrade:
	alembic downgrade -1

# ── Format & Lint ─────────────────────────────────────────────────────────
autoflake:
	autoflake --remove-unused-variables --ignore-init-module-imports \
	          --remove-all-unused-imports -i -r $(LINT_DIRS)

isort:
	isort $(LINT_DIRS)

black:
	black $(LINT_DIRS)

format: isort autoflake black

mypy:
	mypy $(LINT_DIRS)

flake8:
	PYTHONWARNINGS="ignore::UserWarning" flake8 $(LINT_DIRS)

lint: mypy
	isort --check-only --diff $(LINT_DIRS)
	black --check --diff $(LINT_DIRS)
	PYTHONWARNINGS="ignore::UserWarning" flake8 $(LINT_DIRS)

typecheck:
	mypy $(LINT_DIRS)

# Full CI gate.
check: lint test

# ── Tests ─────────────────────────────────────────────────────────────────
test:
	pytest -n auto

test-cov:
	pytest -n auto --cov=dating --cov-branch --cov-report=term-missing --cov-fail-under=70

# ── Docker ────────────────────────────────────────────────────────────────
docker-build:
	docker build -t hintder-api .

docker-run:
	docker run -p 8080:8080 hintder-api
