# Repository Guidelines

## Project Structure & Module Organization
- `src/tm` hosts the FastAPI transaction manager (2PC coordinator); `src/rms/service` exposes per-resource FastAPI services (flight, hotel, car, customer, reservation) backed by the shared RM engine in `src/rm` and request models in `src/rms/models`.
- `src/wc/workflow_controller.py` is the client facade used by tests to drive cross-service transactions.
- `scripts/` contains automation: `create_database.py` spins up MySQL containers with init SQL in `scripts/db-init/`, and `start_service.py` runs uvicorn processes for TM and each RM.
- `test/` holds manual concurrency checks for workflow controller behavior and RM conflict handling.

## Setup, Build & Run
- Requires Python 3.10+ and Docker (used for the MySQL containers).
- Install dependencies with `uv sync` (uses `uv.lock`) or `pip install -e .` to read `pyproject.toml`.
- Bootstrap databases: `python scripts/create_database.py` (starts `mysql:oraclelinux9` containers on ports 33061–33064 with seeded schemas).
- Start services via `python scripts/start_service.py <id>` where `0`=TM(9000), `1`=flight(8001), `2`=hotel(8002), `3`=car(8003), `4`=customer(8004); run each in its own shell or background. Direct uvicorn invocations (e.g., `uvicorn src.tm.transaction_manager:app --reload --port 9000`) are equivalent.
- The workflow controller defaults to the ports above; override URLs in its constructor if you change them.

## Testing Guidelines
- Tests assume all services and MySQL instances are running locally with the seeded schema.
- Resource-manager checks: `python -m test.rm.test` (validates write-write conflict semantics). Verify table/column names align with `scripts/db-init/` before running.
- Workflow controller stress: `python -m test.wc.test` (spawns concurrent transactions; adjust `THREADS`/`ROUNDS` to control load). Clean DB state between runs if results should be isolated.
- Add new tests alongside existing modules; keep concurrency cases deterministic and cover commit/abort paths.

## Coding Style & Naming Conventions
- Use 4-space indentation, type hints where helpful, and FastAPI + Pydantic patterns for request/response models.
- Prefer `snake_case` for modules and functions; preserve existing public API names (e.g., `addFlight`, `reserveFlight`) to avoid breaking callers.
- Keep HTTP routes consistent with the current `/records/*` and `/txn/*` shapes and log via the standard `logging` module.

## Commit & Pull Request Guidelines
- Follow the conventional commits pattern seen in the log (`feat: ...`, `fix: ...`, `refactor: ...`).
- PRs should describe scope, testing performed, and any schema/port changes; link issues when possible and include repro steps or sample requests/responses for API-affecting work.
- Mention external requirements (Docker running, port usage) so reviewers can reproduce locally.

## Architecture Notes
- The system uses two-phase commit: the transaction manager coordinates enlist/prepare/commit/abort across resource managers; the workflow controller orchestrates client flows over those HTTP APIs.
- Resource managers persist to MySQL through a custom page IO, page index, and locking layer; reservation/customer services follow the same RM pattern with different tables.
