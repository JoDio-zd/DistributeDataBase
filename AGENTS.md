# Repository Guidelines

## Project Structure & Module Organization
- `src/tm` hosts the FastAPI transaction manager (2PC coordinator); `src/rms/service` exposes per-resource FastAPI services (flight, hotel, car, customer, reservation) backed by shared RM logic in `src/rm` and request models in `src/rms/models`.
- `src/wc/workflow_controller.py` is the client facade used by tests to drive cross-service transactions.
- `scripts/` holds automation: `create_database.py` spins up MySQL containers with init SQL in `scripts/db-init/`; `start_service.py` runs uvicorn processes for TM and each RM.
- `test/` contains concurrency checks for workflow controller behavior and RM conflict handling.

## Build, Test, and Development Commands
- Install deps: `uv sync` (preferred) or `pip install -e .` from repo root.
- Bootstrap MySQL containers with seeded schema: `python scripts/create_database.py` (uses ports 33061–33064).
- Run services: `python scripts/start_service.py <id>` where `0`=TM(9001), `1`=flight(8001), `2`=hotel(8002), `3`=car(8003), `4`=customer(8004); run each in its own shell. Direct uvicorn is equivalent (e.g., `uvicorn src.tm.transaction_manager:app --reload --port 9001`).
- Tests assume all services and DBs are running: `python -m test.rm.test` for RM conflict semantics; `python -m test.wc.test` for workflow controller stress (tune `THREADS`/`ROUNDS` as needed).

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, type hints where helpful; FastAPI + Pydantic patterns for request/response models.
- Prefer `snake_case` for modules/functions; keep public API names (e.g., `addFlight`, `reserveFlight`) stable for callers.
- Log via standard `logging`; keep HTTP routes aligned with existing `/records/*` and `/txn/*` shapes.

## Testing Guidelines
- Keep concurrency cases deterministic; cover both commit and abort paths.
- Align table/column names with `scripts/db-init/` schema before running tests; reset DB state between runs when comparing results.
- Add new tests alongside existing modules to mirror RM vs workflow controller layers.

## Commit & Pull Request Guidelines
- Use conventional commits seen in history (`feat: ...`, `fix: ...`, `refactor: ...`).
- PRs should state scope, testing performed, and any schema/port changes; link issues when available and include repro steps or sample requests/responses for API changes.
- Note external requirements (Docker running, port usage) so reviewers can reproduce locally.

## Architecture Notes
- Two-phase commit: TM coordinates enlist/prepare/commit/abort across resource managers; workflow controller orchestrates client flows over those HTTP APIs.
- Resource managers persist to MySQL through custom page IO, page index, and locking layers; reservation/customer services reuse the same RM pattern with different tables.
