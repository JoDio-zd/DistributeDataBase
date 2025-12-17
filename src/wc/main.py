"""
WC (Workflow Controller) Main Application

This is the FastAPI application entry point for the Workflow Controller service.
"""

import logging
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import httpx
import uvicorn

from src.wc.config import get_config
from src.wc.middleware import TransactionContextMiddleware
from src.wc.services.tm_client import TMClient
from src.wc.services.rm_client import RMClient
from src.wc.services.orchestrator import ReservationOrchestrator
from src.wc.services.lifecycle import LifecycleManager
from src.wc.exceptions import WCException

# Import routers
from src.wc.routers import transactions, flights, hotels, cars, customers, admin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state for clients
app_state: Dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.

    Handles startup and shutdown:
    - On startup: Initialize HTTP clients and service clients
    - On shutdown: Close HTTP clients
    """
    config = get_config()

    logger.info("Starting WC service...")
    logger.info(f"Configuration: TM={config.tm_base_url}, "
                f"Flights={config.flights_rm_url}, "
                f"Hotels={config.hotels_rm_url}, "
                f"Cars={config.cars_rm_url}, "
                f"Customers={config.customers_rm_url}")

    # Create shared HTTP client with timeout configuration
    timeout = httpx.Timeout(
        connect=config.http_connect_timeout,
        read=config.http_read_timeout,
    )
    http_client = httpx.AsyncClient(timeout=timeout)

    # Initialize TM client
    tm_client = TMClient(
        base_url=config.tm_base_url,
        http_client=http_client
    )

    # Initialize RM clients
    flights_rm = RMClient(
        resource_name="flights",
        base_url=config.flights_rm_url,
        http_client=http_client
    )

    hotels_rm = RMClient(
        resource_name="hotels",
        base_url=config.hotels_rm_url,
        http_client=http_client
    )

    cars_rm = RMClient(
        resource_name="cars",
        base_url=config.cars_rm_url,
        http_client=http_client
    )

    customers_rm = RMClient(
        resource_name="customers",
        base_url=config.customers_rm_url,
        http_client=http_client
    )

    # Initialize orchestrator
    orchestrator = ReservationOrchestrator(
        flights_rm=flights_rm,
        hotels_rm=hotels_rm,
        cars_rm=cars_rm,
        customers_rm=customers_rm,
        tm_client=tm_client
    )

    # Initialize lifecycle manager
    lifecycle_manager = LifecycleManager(
        tm_client=tm_client,
        flights_rm=flights_rm,
        hotels_rm=hotels_rm,
        cars_rm=cars_rm,
        customers_rm=customers_rm,
        state=app_state,
    )

    # Store in app state
    app_state["http_client"] = http_client
    app_state["tm_client"] = tm_client
    app_state["flights_rm"] = flights_rm
    app_state["hotels_rm"] = hotels_rm
    app_state["cars_rm"] = cars_rm
    app_state["customers_rm"] = customers_rm
    app_state["orchestrator"] = orchestrator
    app_state["lifecycle_manager"] = lifecycle_manager
    app_state["config"] = config

    logger.info("WC service started successfully")

    yield

    # Shutdown: close HTTP client
    logger.info("Shutting down WC service...")
    await http_client.aclose()
    logger.info("WC service shut down complete")


# Create FastAPI app
app = FastAPI(
    title="Workflow Controller (WC)",
    description="Workflow Controller for distributed transaction management",
    version="1.0.0",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(TransactionContextMiddleware)

# Include routers
app.include_router(transactions.router, prefix="", tags=["Transactions"])
app.include_router(flights.router, prefix="", tags=["Flights"])
app.include_router(hotels.router, prefix="", tags=["Hotels"])
app.include_router(cars.router, prefix="", tags=["Cars"])
app.include_router(customers.router, prefix="", tags=["Customers"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])


# Exception handlers
@app.exception_handler(WCException)
async def wc_exception_handler(request: Request, exc: WCException):
    """Handle custom WC exceptions."""
    logger.error(
        f"WC Exception: {exc.message}",
        extra={"xid": exc.xid, "status_code": exc.status_code}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=400,
        content={
            "error": "Validation error",
            "details": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "details": str(exc)
        }
    )


# Health check endpoint
@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "service": "Workflow Controller (WC)",
        "status": "running",
        "version": "1.0.0"
    }


# Dependency injection helpers
def get_tm_client() -> TMClient:
    """Get TM client from app state."""
    return app_state["tm_client"]


def get_flights_rm() -> RMClient:
    """Get Flights RM client from app state."""
    return app_state["flights_rm"]


def get_hotels_rm() -> RMClient:
    """Get Hotels RM client from app state."""
    return app_state["hotels_rm"]


def get_cars_rm() -> RMClient:
    """Get Cars RM client from app state."""
    return app_state["cars_rm"]


def get_customers_rm() -> RMClient:
    """Get Customers RM client from app state."""
    return app_state["customers_rm"]


def get_orchestrator() -> ReservationOrchestrator:
    """Get orchestrator from app state."""
    return app_state["orchestrator"]


def get_lifecycle_manager() -> LifecycleManager:
    """Get lifecycle manager from app state."""
    return app_state["lifecycle_manager"]


# CLI entrypoint
if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "src.wc.main:app",
        host=config.wc_host,
        port=config.wc_port,
        reload=False,
        log_level=config.log_level.lower()
    )
