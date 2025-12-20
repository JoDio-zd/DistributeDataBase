# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a distributed database system implementing a travel booking application with Two-Phase Commit (2PC) protocol for coordinating distributed transactions across multiple resource managers. The system demonstrates ACID transaction semantics with hybrid concurrency control (pessimistic locking + optimistic concurrency control).

## Essential Commands

### Environment Setup
```bash
# Install dependencies (Python 3.10+ required)
uv sync  # preferred
# or
pip install -e .

# Bootstrap MySQL containers (ports 33061-33064)
python scripts/create_database.py
```

### Running Services
All services must be running for the system to function. Run each in a separate terminal:
```bash
python scripts/start_service.py 0  # Transaction Manager (port 9001)
python scripts/start_service.py 1  # Flight RM (port 8001)
python scripts/start_service.py 2  # Hotel RM (port 8002)
python scripts/start_service.py 3  # Car RM (port 8003)
python scripts/start_service.py 4  # Customer RM (port 8004)
```

Alternative direct uvicorn approach:
```bash
uvicorn src.tm.transaction_manager:app --reload --port 9001
uvicorn src.rms.service.flight_service:app --reload --port 8001
# etc.
```

### Testing
Tests require all services and databases to be running:
```bash
# Test RM conflict semantics and locking
python -m test.rm.test

# Test workflow controller with concurrent transactions
python -m test.wc.test

# Tune concurrency in test.wc.test by modifying THREADS and ROUNDS variables
```

## Architecture Overview

### Three-Layer Design

**1. Transaction Manager (TM)** - `src/tm/transaction_manager.py`
- Coordinates distributed transactions using Two-Phase Commit protocol
- Port 9001
- Key endpoints:
  - `POST /txn/start` → returns transaction ID (xid)
  - `POST /txn/commit` → executes 2PC (prepare → commit all or abort all)
  - `POST /txn/abort` → aborts transaction
  - `POST /txn/enlist` → registers RM with transaction

**2. Resource Manager Services (RMS)** - `src/rms/service/`
- FastAPI services exposing domain-specific CRUD operations
- Each service wraps a ResourceManager instance backed by MySQL
- Services: flight (8001), hotel (8002), car (8003), customer (8004), reservation (8005)
- API pattern:
  ```
  GET    /records/{key}?xid=<xid>    # Read
  POST   /records                     # Insert
  PUT    /records/{key}               # Update
  DELETE /records/{key}?xid=<xid>     # Delete
  POST   /txn/prepare?xid=<xid>       # 2PC prepare phase
  POST   /txn/commit?xid=<xid>        # 2PC commit phase
  POST   /txn/abort?xid=<xid>         # Abort transaction
  ```

**3. Workflow Controller (WC)** - `src/wc/workflow_controller.py`
- Client facade orchestrating multi-service transactions
- Provides high-level operations: `addFlight()`, `reserveFlight()`, `addCustomer()`, etc.
- Used by test suites to drive cross-service workflows

### Resource Manager Core (`src/rm/`)

The RM layer provides pluggable storage and transaction management:

**Base Abstractions** (`src/rm/base/`):
- `page.py`: Record (versioned dict with delete flag) and Page (collection of records)
- `page_io.py`: Persistence interface (page_in/page_out)
- `page_index.py`: Key-to-page mapping interface
- `page_pool.py`: Buffer pool interface
- `shadow_record_pool.py`: Uncommitted changes tracking
- `err_code.py`: Comprehensive error codes (KEY_EXISTS, KEY_NOT_FOUND, LOCK_CONFLICT, VERSION_CONFLICT, etc.)

**Implementations** (`src/rm/impl/`):
- `lock_manager.py`: Row-level pessimistic locking
- `committed_page_pool.py`: In-memory cache for committed pages
- `simple_shadow_record_pool.py`: Per-transaction shadow records for isolation
- `page_io/mysql_page_io.py`: MySQL persistence (single key)
- `page_io/mysql_multi_index_page_io.py`: MySQL persistence (multi-key support)
- `page_index/`: Multiple indexing strategies (ordered, direct, linear)

**ResourceManager** (`src/rm/resource_manager.py`):
- Core transaction logic combining pessimistic locking + OCC
- CRUD operations: `read()`, `add()`, `update()`, `delete()`
- 2PC participant:
  - `prepare()`: Validates no write-write conflicts via version checking
  - `commit()`: Persists shadow records to committed pool and MySQL
  - `abort()`: Discards shadow records, releases locks

### Concurrency Control Strategy

**Hybrid Approach**:
1. **Pessimistic Locking** (write-time):
   - `RowLockManager` prevents concurrent writes to same key
   - Lock held until transaction commit/abort

2. **Optimistic Concurrency Control** (commit-time):
   - Version numbers track record modifications
   - `prepare()` validates: no other transaction modified records since read
   - Detects write-write conflicts and aborts if validation fails

**Isolation Mechanism**:
- Shadow records: Uncommitted changes stored separately per transaction
- Version tracking: Each record has version number incremented on commit
- Start versions: Transaction tracks version of each record at first read

### Transaction Flow

```
1. WC calls TM: POST /txn/start → returns xid
2. WC calls RM services with xid for business operations
3. RMs automatically enlist with TM on first operation
4. RMs acquire locks and create shadow records
5. On commit:
   - TM Phase 1 (Prepare): Request prepare from all enrolled RMs
   - RMs validate versions, respond ok/not-ok
   - TM Phase 2: If all RMs vote ok → commit all; else → abort all
6. On abort:
   - RMs discard shadows and release locks
```

## Key Implementation Details

### Database Schema
Each RM service has dedicated MySQL container with specific schema:
- Flight: `flightNum` (PK), `price`, `numSeats`, `numAvail`
- Hotel: `location` (PK), `price`, `numRooms`, `numAvail`
- Car: `location` (PK), `price`, `numCars`, `numAvail`
- Customer: `custName` (PK), plus reservation tracking columns
- Reservation: `resvKey` (PK), `custName`, `resvType`

Schemas initialized from `scripts/db-init/{service}/init.sql`

### Page Size and Indexing
- Configurable page size (e.g., `page_size = 2` in services)
- Key width padding (e.g., `key_width = 4` → "123" becomes "0123")
- Multiple page index implementations available for different access patterns

### Request Models
Defined in `src/rms/models/models.py`:
- `InsertRequest`: xid, key, value dict
- `UpdateRequest`: xid, key, updates dict
- `TxnRequest`: xid only (for prepare/commit/abort)

Error handling in `src/rms/base/err_handle.py` maps `RMResult` error codes to HTTP status codes.

## Development Guidelines

### Code Style
- Python 3.10+, 4-space indentation, type hints where helpful
- `snake_case` for modules/functions
- Keep public API names stable (e.g., `addFlight`, `reserveFlight`)
- Use standard `logging` library

### When Modifying RMs
- Understand the layering: base abstractions → implementations → ResourceManager → services
- Test concurrent scenarios: read-write conflicts, write-write conflicts
- Verify both commit and abort paths work correctly
- Reset DB state between test runs when comparing results

### When Modifying TM
- 2PC protocol is safety-critical: all RMs must agree on outcome
- Handle network failures gracefully in both phases
- Thread-safety: protect shared state with `_lock`

### When Adding New Services
1. Create SQL schema in `scripts/db-init/{service}/init.sql`
2. Add MySQL container setup in `scripts/create_database.py`
3. Implement service in `src/rms/service/{service}_service.py`
4. Configure ResourceManager with appropriate PageIO and PageIndex
5. Update `scripts/start_service.py` with new service ID

### Testing Patterns
- Keep concurrency tests deterministic where possible
- Cover edge cases: transaction abort, lock conflicts, version conflicts
- Align table/column names with DB schema before running tests
- Tests in `test/rm/` focus on RM semantics; `test/wc/` focus on workflow coordination

### Commit Conventions
Follow patterns from git history:
- `feat: ...` for new features
- `fix: ...` for bug fixes
- `refactor: ...` for code restructuring
- `chore: ...` for maintenance tasks
- `test: ...` for test additions/changes
