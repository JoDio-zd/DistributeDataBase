"""
WC (Workflow Controller) Middleware

This module provides middleware for X-Transaction-Id handling and logging.
"""

import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
SERVICE_AVAILABLE = True


def set_service_availability(is_available: bool) -> None:
    """
    Toggle service availability. When False, non-admin requests return 503.
    """
    global SERVICE_AVAILABLE
    SERVICE_AVAILABLE = is_available


class TransactionContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and store X-Transaction-Id from request headers.

    This middleware:
    1. Extracts X-Transaction-Id from request headers
    2. Stores it in request.state for use by route handlers
    3. Logs all requests with xid for traceability
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process each request and extract transaction context.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            Response from the route handler
        """
        # Extract X-Transaction-Id from headers
        xid = request.headers.get("X-Transaction-Id") or request.headers.get("x-transaction-id")

        # Store in request state for easy access
        request.state.xid = xid

        # Record start time for latency measurement
        start_time = time.time()

        # Log incoming request
        logger.info(
            f"Incoming request: {request.method} {request.url.path}",
            extra={
                "xid": xid,
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else None,
            }
        )

        # Short-circuit if service is marked unavailable (allow admin endpoints)
        if not SERVICE_AVAILABLE and not request.url.path.startswith("/admin"):
            return JSONResponse(
                status_code=503,
                content={"error": "Service is unavailable", "xid": xid},
            )

        # Process request
        try:
            response = await call_next(request)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Log response
            logger.info(
                f"Request completed: {request.method} {request.url.path} - Status: {response.status_code}",
                extra={
                    "xid": xid,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                }
            )

            return response

        except Exception as e:
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Log error
            logger.error(
                f"Request failed: {request.method} {request.url.path} - Error: {str(e)}",
                extra={
                    "xid": xid,
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "latency_ms": round(latency_ms, 2),
                },
                exc_info=True
            )
            raise


def get_transaction_id(request: Request) -> str | None:
    """
    Helper function to get transaction ID from request state.

    Args:
        request: The FastAPI request object

    Returns:
        Transaction ID if present, None otherwise
    """
    return getattr(request.state, "xid", None)
