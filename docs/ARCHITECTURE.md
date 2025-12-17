# WC (Workflow Controller) Architecture

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Component Design](#component-design)
- [Transaction Flow](#transaction-flow)
- [Design Decisions](#design-decisions)
- [Error Handling Strategy](#error-handling-strategy)
- [Key Patterns](#key-patterns)
- [Scalability Considerations](#scalability-considerations)

---

## Overview

The Workflow Controller (WC) is the **client-facing gateway** in a distributed database system implementing the Two-Phase Commit (2PC) protocol. It serves as the single entry point for all client requests, orchestrating transactions across multiple Resource Managers (RMs) and coordinating with a Transaction Manager (TM).

### Design Goals

1. **Simplicity**: Single entry point for all client operations
2. **Reliability**: Automatic error handling with transaction rollback
3. **Transparency**: Hide distributed transaction complexity from clients
4. **Observability**: Structured logging with transaction context
5. **Maintainability**: Clear separation of concerns with modular architecture

### Technology Stack

- **FastAPI**: Modern async web framework with automatic API documentation
- **httpx**: Async HTTP client for TM/RM communication
- **Pydantic**: Type-safe data validation and configuration management
- **Python 3.10+**: Modern Python with type hints and async/await

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          Clients                            │
│                    (curl, Python, Web)                      │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP REST API
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Workflow Controller (WC)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              FastAPI Application                      │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐    │  │
│  │  │ Middleware │  │  Routers   │  │  Services  │    │  │
│  │  │  (X-TID)   │  │  (API)     │  │ (Clients)  │    │  │
│  │  └────────────┘  └────────────┘  └────────────┘    │  │
│  └──────────────────────────────────────────────────────┘  │
└───────────┬────────────────────────────┬────────────────────┘
            │                            │
            │ HTTP                       │ HTTP
            ▼                            ▼
┌───────────────────┐      ┌─────────────────────────────────┐
│  Transaction      │      │     Resource Managers (RMs)     │
│  Manager (TM)     │◄────►│  ┌──────┐ ┌──────┐ ┌──────┐   │
│                   │ 2PC  │  │Flight│ │Hotel │ │ Car  │   │
│  - Global xid     │      │  │  RM  │ │  RM  │ │  RM  │   │
│  - 2PC protocol   │      │  └──────┘ └──────┘ └──────┘   │
│  - Transaction    │      │  ┌────────────┐                │
│    status         │      │  │ Customer   │                │
└───────────────────┘      │  │    RM      │                │
                           │  └────────────┘                │
                           └─────────────────────────────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │   MySQL Databases   │
                           │   (4 containers)    │
                           └─────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| **WC** | Client gateway, transaction orchestration | FastAPI service (src/wc/) |
| **TM** | Global transaction coordinator, 2PC protocol | External dependency (HTTP API) |
| **RMs** | Data management, shadow pages, 2PC participants | External dependency (HTTP API) |
| **Clients** | Business logic, transaction management | User applications |

---

## Component Design

### Directory Structure

```
src/wc/
├── main.py                    # FastAPI app entry point
├── config.py                  # Configuration management
├── models.py                  # Pydantic data models
├── exceptions.py              # Custom exceptions
├── middleware.py              # X-Transaction-Id middleware
├── routers/                   # API route handlers
│   ├── transactions.py        # Transaction lifecycle
│   ├── flights.py             # Flights CRUD + reserve
│   ├── hotels.py              # Hotels CRUD + reserve
│   ├── cars.py                # Cars CRUD + reserve
│   ├── customers.py           # Customers CRUD + reservations query
│   └── admin.py               # Admin operations (die/reconnect)
└── services/                  # Business logic layer
    ├── tm_client.py           # TM communication
    ├── rm_client.py           # RM communication (generic)
    ├── orchestrator.py        # Cross-RM reservation logic
    └── lifecycle.py           # Reconnect/die logic
```

### Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│                  API Layer (Routers)                │  ◄─ HTTP endpoints
│  - Request validation (Pydantic)                    │
│  - Response serialization                           │
│  - Error handling                                   │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│              Business Logic Layer                   │
│  - Orchestrator: Cross-RM operations                │  ◄─ Business logic
│  - Lifecycle: Reconnect/die logic                   │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│            Communication Layer (Clients)            │
│  - TMClient: TM communication                       │  ◄─ External calls
│  - RMClient: RM communication                       │
│  - Error handling + retry logic                     │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│                Infrastructure Layer                 │
│  - httpx: HTTP client                               │  ◄─ Network
│  - Middleware: X-Transaction-Id                     │
│  - Logging: Structured logs                         │
└─────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Configuration Management (`config.py`)

```python
class WCConfig(BaseSettings):
    # Service URLs
    tm_base_url: str
    flights_rm_url: str
    hotels_rm_url: str
    cars_rm_url: str
    customers_rm_url: str

    # Behavior flags
    auto_abort_on_error: bool = True
```

**Design Rationale**:
- Uses Pydantic Settings for type-safe configuration
- Supports environment variables and .env files
- Validation at startup (fail-fast)
- Easy to test with different configs

#### 2. TM Client (`services/tm_client.py`)

**Responsibilities**:
- Start transactions (get xid)
- Commit transactions (trigger 2PC)
- Abort transactions (trigger rollback)
- Query transaction status

**Key Methods**:
```python
async def start_transaction() -> str
async def commit(xid: str) -> dict
async def abort(xid: str) -> dict
async def get_status(xid: str) -> dict
```

**Error Handling**:
- Timeout → IN_DOUBT status
- Connection error → Raise TMCommunicationError
- 4xx/5xx → Parse and raise appropriate exception

#### 3. RM Client (`services/rm_client.py`)

**Responsibilities**:
- Generic CRUD operations for any RM
- Automatic X-Transaction-Id header injection
- Reserve operations (inventory decrement)
- Reservation record management (Customers RM only)

**Key Methods**:
```python
async def add(xid: str, data: dict) -> dict
async def query(xid: str, key: str) -> dict
async def update(xid: str, key: str, data: dict) -> dict
async def delete(xid: str, key: str) -> dict
async def reserve(xid: str, key: str, quantity: int = 1) -> dict
```

**Design Pattern**: Single client class for all RMs (DRY principle)

#### 4. Reservation Orchestrator (`services/orchestrator.py`)

**Responsibilities**:
- Coordinate cross-RM reserve operations
- Ensure atomicity of multi-step operations

**Reserve Operation Flow**:
```python
async def reserve_flight(xid, flight_num, cust_name, quantity=1):
    # Step 1: Decrement inventory (Flights RM)
    await flights_rm.reserve(xid, flight_num, quantity)

    # Step 2: Add reservation record (Customers RM)
    await customers_rm.add_reservation(xid, {
        "custName": cust_name,
        "resvType": "FLIGHT",
        "resvKey": flight_num
    })

    # If any step fails → exception → auto-abort
```

**Why Separate Orchestrator?**
- Clear separation of concerns
- Easier to test complex workflows
- Reusable across multiple routers
- Centralized transaction logic

#### 5. Middleware (`middleware.py`)

**X-Transaction-Id Middleware**:
```python
class TransactionContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        xid = request.headers.get("X-Transaction-Id")
        request.state.xid = xid
        # Add xid to log context
        logger.info("Request received", xid=xid, path=request.url.path)
        response = await call_next(request)
        return response
```

**Benefits**:
- Automatic transaction context propagation
- All logs include xid
- No need to pass xid manually
- Accessible via `request.state.xid`

---

## Transaction Flow

### 1. Simple Query Flow

```
Client                    WC                      RM
  │                       │                       │
  ├─POST /transactions───►│                       │
  │                       ├─POST /transactions───►│ (TM)
  │                       │◄──xid: "abc123"──────┤
  │◄──xid: "abc123"──────┤                       │
  │                       │                       │
  ├─GET /flights/CA1234──►│                       │
  │ (X-Transaction-Id: abc)                      │
  │                       ├─GET /flights/CA1234──►│ (Flights RM)
  │                       │  (X-Transaction-Id: abc)
  │                       │◄──flight data────────┤
  │◄──flight data────────┤                       │
  │                       │                       │
  ├─POST /transactions/abc/commit─────────────────►│
  │                       ├─POST /transactions/abc/commit─►│ (TM)
  │                       │  (TM triggers 2PC with all RMs)
  │                       │◄──status: COMMITTED──┤
  │◄──status: COMMITTED──┤                       │
```

### 2. Reservation Flow (Cross-RM)

```
Client                    WC                   Flights RM      Customers RM
  │                       │                       │               │
  ├─POST /transactions───►│                       │               │
  │◄──xid: "xyz"─────────┤                       │               │
  │                       │                       │               │
  ├─POST /flights/CA1234/reservations──────────────────────────────►│
  │ (X-Transaction-Id: xyz)                     │               │
  │ Body: {"custName": "Alice", "quantity": 1}  │               │
  │                       │                       │               │
  │                       ├──Step 1: Reserve────►│               │
  │                       │  POST /flights/CA1234/reserve         │
  │                       │  (X-Transaction-Id: xyz)              │
  │                       │◄──numAvail: 199─────┤               │
  │                       │                       │               │
  │                       ├──Step 2: Add Reservation─────────────►│
  │                       │  POST /reservations                   │
  │                       │  (X-Transaction-Id: xyz)              │
  │                       │  Body: {custName: "Alice", resvType: "FLIGHT", ...}
  │                       │◄──success───────────────────────────┤
  │◄──success────────────┤                       │               │
  │                       │                       │               │
  ├─POST /transactions/xyz/commit─────────────────────────────────►│
  │                       │  (TM triggers 2PC: Flights RM + Customers RM)
  │◄──status: COMMITTED──┤                       │               │
```

### 3. Error with Auto-Abort Flow

```
Client                    WC                   Flights RM        TM
  │                       │                       │               │
  ├─POST /transactions───►│                       │               │
  │◄──xid: "err"─────────┤                       │               │
  │                       │                       │               │
  ├─POST /flights/INVALID/reservations──────────────────────────────►│
  │ (X-Transaction-Id: err)                     │               │
  │                       │                       │               │
  │                       ├─POST /flights/INVALID/reserve────────►│
  │                       │  (X-Transaction-Id: err)              │
  │                       │◄──404 Not Found─────┤               │
  │                       │                       │               │
  │                       │  WC detects error                     │
  │                       │  AUTO_ABORT_ON_ERROR=true             │
  │                       │                       │               │
  │                       ├─POST /transactions/err/abort─────────►│
  │                       │◄──status: ABORTED───────────────────┤
  │                       │                       │               │
  │◄──ERROR + "transaction_aborted": true───────┤               │
```

---

## Design Decisions

### 1. Why FastAPI?

**Alternatives Considered**: Flask, Django REST Framework

**Reasons for FastAPI**:
- ✅ Native async/await support (critical for concurrent RM calls)
- ✅ Automatic API documentation (Swagger/ReDoc)
- ✅ Built-in request validation (Pydantic)
- ✅ High performance (Starlette + uvicorn)
- ✅ Modern Python development experience
- ✅ Excellent error handling and dependency injection

### 2. Why Generic RMClient?

**Alternatives Considered**: Separate client for each RM type

**Reasons for Generic Client**:
- ✅ DRY principle (same CRUD logic for all RMs)
- ✅ Easy to add new RMs (just instantiate with URL)
- ✅ Consistent error handling across all RMs
- ✅ Less code to maintain

**Trade-off**: Slightly less type-safe (Customers RM has unique methods)

### 3. Why Separate Orchestrator?

**Alternatives Considered**: Embed logic in routers

**Reasons for Orchestrator**:
- ✅ Single Responsibility Principle (routers handle HTTP, orchestrator handles business logic)
- ✅ Easier to test (can test orchestrator independently)
- ✅ Reusable across multiple endpoints
- ✅ Clear transaction semantics

### 4. Auto-Abort Strategy

**Alternatives Considered**: Manual abort by clients

**Reasons for Auto-Abort**:
- ✅ Prevents inconsistent states
- ✅ Simpler client code
- ✅ Fail-fast principle
- ✅ Clear error semantics

**Trade-off**: Less flexibility (can't retry operations)

### 5. X-Transaction-Id Propagation

**Alternatives Considered**: Pass xid in request body, query parameters

**Reasons for Header**:
- ✅ RESTful best practice (metadata in headers)
- ✅ Doesn't pollute request bodies
- ✅ Middleware can extract automatically
- ✅ Easy to add to logs

---

## Error Handling Strategy

### Error Hierarchy

```
WCException (Base)
├── TMCommunicationError        # TM unreachable or error
├── RMCommunicationError        # RM unreachable or error
├── ResourceNotFoundError       # 404 from RM
├── ResourceConflictError       # 409 from RM (e.g., duplicate key)
├── InsufficientAvailabilityError  # Reserve failed (no inventory)
└── CommitTimeoutError          # Commit timed out (IN_DOUBT)
```

### Error Handling Flow

```python
try:
    # Business operation (e.g., reserve flight)
    result = await flights_rm.reserve(xid, flight_num)
except RMCommunicationError as e:
    # Auto-abort if configured
    if config.auto_abort_on_error:
        try:
            await tm_client.abort(xid)
            logger.warning("Auto-aborted transaction", xid=xid, reason=str(e))
        except Exception as abort_error:
            logger.error("Auto-abort failed", xid=xid, error=str(abort_error))

    # Return error to client
    raise HTTPException(
        status_code=502,
        detail={
            "error": str(e),
            "transaction_aborted": config.auto_abort_on_error,
            "xid": xid
        }
    )
```

**Router-level auto-abort**: All resource CRUD/reserve endpoints wrap RM/TM errors and trigger `abort(xid)` automatically when `auto_abort_on_error` is enabled, to align with the “失败自动触发abort” requirement.

### HTTP Status Code Mapping

| Status Code | Meaning | WC Action |
|-------------|---------|-----------|
| 404 | Resource not found | Return 404, auto-abort if enabled |
| 409 | Conflict (duplicate key, insufficient inventory) | Return 409, auto-abort if enabled |
| 500 | RM internal error | Return 502, auto-abort if enabled |
| 503 | RM unavailable | Return 503, auto-abort if enabled |
| Timeout | Request timed out | Return 504, auto-abort if enabled |

**Commit timeout**: TM commit responses with `status="IN_DOUBT"` are surfaced directly to clients so they can query `/transactions/{xid}` for the final decision.

---

## Key Patterns

### 1. Dependency Injection Pattern

```python
# main.py
async def get_tm_client() -> TMClient:
    return app.state.tm_client

# routers/transactions.py
@router.post("/transactions")
async def start_transaction(
    tm_client: TMClient = Depends(get_tm_client)
):
    xid = await tm_client.start_transaction()
    return {"xid": xid}
```

**Benefits**:
- Easy to test (can inject mock clients)
- Clear dependencies
- Singleton management

### 2. Middleware Pattern

**X-Transaction-Id Middleware**: Extracts transaction ID from headers and adds to request state

**Benefits**:
- Automatic context propagation
- Consistent logging
- No manual parameter passing

### 3. Orchestrator Pattern

**Cross-RM Coordination**: Separates multi-step business logic from API handlers

**Benefits**:
- Single Responsibility Principle
- Testability
- Reusability

### 4. Circuit Breaker (Future Enhancement)

**Not Implemented**: Would retry failed RM calls with exponential backoff

**Why Not Yet**:
- Adds complexity
- v1 focuses on correctness over resilience
- Can be added later without API changes

---

## Scalability Considerations

### Current Limitations (v1)

1. **Single WC Instance**: No support for horizontal scaling yet
   - **Solution**: Add load balancer + stateless WC (transactions are in TM)

2. **Synchronous RM Calls**: Reserve operations are sequential
   - **Solution**: Parallel RM calls where possible (future optimization)

3. **No Connection Pool**: httpx client uses default pool
   - **Solution**: Configure connection limits in production

4. **No Caching**: All queries hit RMs directly
   - **Solution**: Add Redis cache for read-heavy workloads

### Scalability Roadmap

#### Phase 1: Horizontal Scaling (Current v1)
- ✅ Stateless WC design (all state in TM)
- ✅ Load balancer ready (no session state)
- ⏳ Health check endpoint (TODO)

#### Phase 2: Performance Optimization
- ⏳ Connection pool tuning
- ⏳ Parallel RM queries (where safe)
- ⏳ Request batching

#### Phase 3: High Availability
- ⏳ Circuit breaker pattern
- ⏳ Retry with exponential backoff
- ⏳ Fallback mechanisms

---

## Testing Strategy

### Unit Tests (Future)

```python
# tests/test_orchestrator.py
async def test_reserve_flight_success():
    """Test successful flight reservation"""
    mock_flights_rm = Mock()
    mock_customers_rm = Mock()
    orchestrator = ReservationOrchestrator(
        flights_rm=mock_flights_rm,
        customers_rm=mock_customers_rm
    )

    result = await orchestrator.reserve_flight("xid", "CA1234", "Alice")

    mock_flights_rm.reserve.assert_called_once_with("xid", "CA1234", 1)
    mock_customers_rm.add_reservation.assert_called_once()
```

### Integration Tests (Future)

- Test full transaction flow with mock TM/RMs
- Test error scenarios (RM failure, TM timeout)
- Test auto-abort behavior

### Manual Testing (Current)

- Use curl commands (see README.md)
- Use Swagger UI at http://localhost:8000/docs

---

## Security Considerations

### Current Security Measures

1. **No Authentication/Authorization**: v1 assumes trusted network
   - **Future**: Add API keys or OAuth2

2. **Input Validation**: Pydantic validates all request bodies
   - ✅ Type checking
   - ✅ Required field validation
   - ✅ Range validation

3. **SQL Injection**: Not applicable (RMs handle database access)

4. **CORS**: Configurable for web clients

### Production Hardening Checklist

- [ ] Add authentication (API keys)
- [ ] Add authorization (role-based access)
- [ ] Add rate limiting
- [ ] Disable /admin/die endpoint
- [ ] Enable HTTPS
- [ ] Add request ID for tracing
- [ ] Add audit logging

---

## Monitoring and Observability

### Logging

**Structured Logs** (JSON format in production):
```json
{
  "timestamp": "2023-12-17T10:30:45Z",
  "level": "INFO",
  "message": "Transaction started",
  "xid": "abc123",
  "client_ip": "192.168.1.100"
}
```

**Key Log Events**:
- Transaction lifecycle (start/commit/abort)
- RM communication (request/response)
- Errors and auto-abort triggers

### Metrics (Future)

**Key Metrics to Track**:
- Transaction throughput (txn/sec)
- Transaction latency (p50, p95, p99)
- RM communication latency
- Error rate by type
- Auto-abort rate

**Tools**: Prometheus + Grafana

### Tracing (Future)

**Distributed Tracing**: OpenTelemetry
- Trace transaction flow across WC → TM → RMs
- Visualize latency bottlenecks

---

## Deployment

### Development

```bash
# Using uvicorn directly
uvicorn src.wc.main:app --reload

# Using Python module
python -m src.wc.main
```

### Production

```bash
# Using gunicorn + uvicorn workers
gunicorn src.wc.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Docker (Future)

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install -e .
CMD ["uvicorn", "src.wc.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## References

### External Dependencies

- **TM Interface**: See `docs/API_CONTRACTS.md` (TM Interface Specification)
- **RM Interface**: See `docs/API_CONTRACTS.md` (RM Interface Specification)

### Related Documentation

- `README.md`: User guide and quick start
- `docs/API_CONTRACTS.md`: Complete TM/RM interface specifications
- `wc需求文档.md`: Original requirements (Chinese)

### Further Reading

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Two-Phase Commit Protocol](https://en.wikipedia.org/wiki/Two-phase_commit_protocol)
- [Distributed Transactions](https://martinfowler.com/articles/patterns-of-distributed-systems/)

---

**Architecture Version**: 1.0.0
**Last Updated**: 2023-12-17
**Status**: ✅ Implementation Complete
