.PHONY: install lint format typecheck test coverage docs docs-serve precommit

install:
	uv sync --all-extras

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

test:
	uv run pytest

coverage:
	uv run pytest --cov=uvb76_gen --cov-report=term-missing

docs:
	uv run mkdocs build

docs-serve:
	uv run mkdocs serve -a 0.0.0.0:8000

precommit:
	uv run pre-commit run --all-files

.PHONY: tts

tts:
	bash scripts/piper_tts.sh
