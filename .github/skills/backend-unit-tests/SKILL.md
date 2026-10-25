---
name: backend-unit-tests
description: "Use when adding or updating Python unit tests for FastAPI backend changes in backend/app, using the repository's pytest conventions."
---

# Backend unit tests

1. Read nearby tests, `backend/tests/conftest.py`, and `backend/tests/mocks.py` before introducing fixtures or mocks.
2. Add tests under `backend/tests/`, mirroring the relevant `app/` feature structure where practical.
3. Use pytest and existing fixtures. Keep tests isolated from external services and real credentials.
4. Cover meaningful success, validation, and failure behavior without duplicating existing assertions.
5. Do not modify production code or dependency configuration to make a test pass.
6. The workflow verifies changes with `python -m pytest --cov=app --cov-report=term-missing` from `backend/`; do not claim the command passed before that step runs.
