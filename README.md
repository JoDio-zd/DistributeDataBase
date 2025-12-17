# Distributed Database System - Workflow Controller (WC)

A distributed transaction management system implementing the Workflow Controller (WC) component with Two-Phase Commit (2PC) protocol support.

## Overview

The Workflow Controller (WC) serves as the **single entry point** for all client requests, coordinating distributed transactions across multiple Resource Managers (RMs) and a Transaction Manager (TM).

### Architecture Components

- **WC (Workflow Controller)**: Client-facing service for transaction orchestration (**Implemented**)
- **TM (Transaction Manager)**: Global transaction coordinator implementing 2PC (**External dependency**)
- **RMs (Resource Managers)**: Data managers for Flights, Hotels, Cars, and Customers (**External dependency**)

## Quick Start

### Prerequisites

- Python 3.10+
- Docker (for MySQL databases)
- Running TM and RM services (see API contracts)

### Installation

1. **Install dependencies:**
   ```bash
   pip install -e .
   # or using uv
   uv pip install -e .
   ```

2. **Set up MySQL databases (for RMs):**
   ```bash
   python scripts/create_database.py
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your TM/RM URLs
   ```

### Running the WC Service

```bash
# Method 1: Using Python module
python -m src.wc.main

# Method 2: Using uvicorn directly
uvicorn src.wc.main:app --host 0.0.0.0 --port 8000 --reload

# Method 3: Using Python script
python src/wc/main.py
```

The service will start on `http://localhost:8000`.

### Verify Installation

```bash
curl http://localhost:8000
# Expected: {"service":"Workflow Controller (WC)","status":"running","version":"1.0.0"}
```

## API Documentation

Once the WC service is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key API Endpoints

#### Transaction Management

- `POST /transactions` - Start a new transaction
- `POST /transactions/{xid}/commit` - Commit transaction
- `POST /transactions/{xid}/abort` - Abort transaction
- `GET /transactions/{xid}` - Query transaction status
  - Commit timeout returns `status: "IN_DOUBT"` with a message

#### Resource Operations

- **Flights**: `/flights`, `/flights/{flightNum}`, `/flights/{flightNum}/reservations`
- **Hotels**: `/hotels`, `/hotels/{location}`, `/hotels/{location}/reservations`
- **Cars**: `/cars`, `/cars/{location}`, `/cars/{location}/reservations`
- **Customers**: `/customers`, `/customers/{custName}`, `/customers/{custName}/reservations`

#### Admin Operations

- `POST /admin/reconnect` - Reconnect to TM/RMs and rebuild HTTP clients
- `POST /admin/die` - Mark WC unavailable (503). Add `?hard=true` to exit the process.

## Usage Examples

### Example 1: Simple Flight Query

```bash
# Start transaction
xid=$(curl -X POST http://localhost:8000/transactions | jq -r '.xid')

# Query a flight
curl -H "X-Transaction-Id: $xid" \
     http://localhost:8000/flights/CA1234

# Commit transaction
curl -X POST http://localhost:8000/transactions/$xid/commit
```

### Example 2: Flight Reservation

```bash
# Start transaction
xid=$(curl -X POST http://localhost:8000/transactions | jq -r '.xid')

# Create customer
curl -X POST http://localhost:8000/customers \
     -H "X-Transaction-Id: $xid" \
     -H "Content-Type: application/json" \
     -d '{"custName": "Alice"}'

# Reserve flight
curl -X POST http://localhost:8000/flights/CA1234/reservations \
     -H "X-Transaction-Id: $xid" \
     -H "Content-Type: application/json" \
     -d '{"custName": "Alice", "quantity": 1}'

# Commit transaction
curl -X POST http://localhost:8000/transactions/$xid/commit
```

### Example 3: Error Handling with Auto-Abort

```bash
# Start transaction
xid=$(curl -X POST http://localhost:8000/transactions | jq -r '.xid')

# Try to reserve non-existent flight (will fail)
curl -X POST http://localhost:8000/flights/INVALID/reservations \
     -H "X-Transaction-Id: $xid" \
     -H "Content-Type: application/json" \
     -d '{"custName": "Bob", "quantity": 1}'
# Transaction is automatically aborted due to AUTO_ABORT_ON_ERROR=true

# Check transaction status
curl http://localhost:8000/transactions/$xid
# Expected: {"xid": "...", "status": "ABORTED"}
```

## Configuration

All configuration is managed via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `WC_HOST` | 0.0.0.0 | WC service host |
| `WC_PORT` | 8000 | WC service port |
| `TM_BASE_URL` | http://localhost:8001 | TM service URL |
| `FLIGHTS_RM_URL` | http://localhost:8002 | Flights RM URL |
| `HOTELS_RM_URL` | http://localhost:8003 | Hotels RM URL |
| `CARS_RM_URL` | http://localhost:8004 | Cars RM URL |
| `CUSTOMERS_RM_URL` | http://localhost:8005 | Customers RM URL |
| `AUTO_ABORT_ON_ERROR` | true | Auto-abort on error |
| `LOG_LEVEL` | INFO | Logging level |

## Development

### Project Structure

```
src/wc/
├── main.py                 # FastAPI app entry point
├── config.py               # Configuration management
├── models.py               # Pydantic data models
├── exceptions.py           # Custom exceptions
├── middleware.py           # X-Transaction-Id middleware
├── routers/                # API route handlers
│   ├── transactions.py     # Transaction APIs
│   ├── flights.py          # Flights APIs
│   ├── hotels.py           # Hotels APIs
│   ├── cars.py             # Cars APIs
│   ├── customers.py        # Customers APIs
│   └── admin.py            # Admin APIs
└── services/               # Business logic
    ├── tm_client.py        # TM communication
    ├── rm_client.py        # RM communication
    ├── orchestrator.py     # Cross-RM reserve logic
    └── lifecycle.py        # Reconnect/die logic
```

### Key Features

- Automatic transaction context propagation via X-Transaction-Id
- Automatic abort on reserve failures
- Cross-RM reservation orchestration
- Structured logging with transaction ID
- Comprehensive error handling
- Auto-generated Swagger/ReDoc documentation

## Documentation

- **[API Contracts](docs/API_CONTRACTS.md)**: Complete TM/RM interface specifications
- **[Architecture](docs/ARCHITECTURE.md)**: System architecture and design decisions
- **[Requirements](wc需求文档.md)**: Original requirements document (Chinese)

## Testing

### Manual Testing with curl

See usage examples above.

### Testing Reconnect

```bash
# Restart TM or RM services, then:
curl -X POST http://localhost:8000/admin/reconnect

# Check response for connection status
```

### Testing Die/Recovery

```bash
# Trigger WC failure
curl -X POST http://localhost:8000/admin/die

# Restart WC service
python -m src.wc.main

# Reconnect to services
curl -X POST http://localhost:8000/admin/reconnect
```

## Important Notes

### TM and RM Dependencies

WC assumes TM and RM services are available at the configured URLs. If they don't exist:

1. **TM**: Implement according to `docs/API_CONTRACTS.md` (TM Interface Specification)
2. **RMs**: Implement HTTP wrappers around the existing `src/rm/resource_manager.py`

### Transaction Guarantees

- **Atomicity**: All-or-nothing via 2PC coordinated by TM
- **Isolation**: Shadow page mechanism in RMs
- **Durability**: Commit persists changes to MySQL
- **Consistency**: Cross-RM operations are atomic

### Auto-Abort Behavior

When `AUTO_ABORT_ON_ERROR=true` (default):
- Any resource operation (CRUD/reserve) failure with an xid triggers automatic abort
- Reserve flow errors trigger automatic abort
- Client receives error response with `transaction_aborted: true`
- No manual abort needed

## Troubleshooting

### WC Can't Connect to TM/RM

1. Check TM/RM services are running
2. Verify URLs in `.env` are correct
3. Check firewall/network connectivity
4. Use `/admin/reconnect` to re-establish connections

### Transaction Stuck in IN_DOUBT

If commit times out:
```bash
# Query final status
curl http://localhost:8000/transactions/$xid
```

### Logs Show Connection Errors

```bash
# Check service health
curl http://localhost:8001  # TM
curl http://localhost:8002  # Flights RM
# ...etc
```

## License

This project is part of the Fudan University Distributed Database course.

## Acknowledgments

- FastAPI for excellent async web framework
- Anthropic Claude for implementation assistance
- Fudan University Database Course Team

---

**Status**: **WC Implementation Complete**
**Version**: 1.0.0
**Last Updated**: 2023-12-17
