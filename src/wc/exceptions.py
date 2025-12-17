"""
WC (Workflow Controller) Custom Exceptions

This module defines custom exception classes for the WC service,
providing clear error handling and automatic abort mechanisms.
"""

from typing import Optional


class WCException(Exception):
    """
    Base exception class for all WC-related errors.

    All custom exceptions should inherit from this class.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[str] = None,
        xid: Optional[str] = None,
    ):
        """
        Initialize WCException.

        Args:
            message: Human-readable error message
            status_code: HTTP status code to return
            details: Additional error details (optional)
            xid: Transaction ID associated with this error (optional)
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details
        self.xid = xid

    def to_dict(self) -> dict:
        """Convert exception to dict for JSON response."""
        result = {
            "error": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.xid:
            result["xid"] = self.xid
        return result


class TMCommunicationError(WCException):
    """
    Exception raised when communication with TM fails.

    This error automatically triggers abort if auto_abort_on_error is enabled.
    """

    def __init__(
        self,
        message: str = "Failed to communicate with Transaction Manager",
        details: Optional[str] = None,
        xid: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            status_code=503,
            details=details,
            xid=xid,
        )


class RMCommunicationError(WCException):
    """
    Exception raised when communication with RM fails.

    This error automatically triggers abort if auto_abort_on_error is enabled.
    """

    def __init__(
        self,
        rm_name: str,
        message: str = "Failed to communicate with Resource Manager",
        details: Optional[str] = None,
        xid: Optional[str] = None,
    ):
        super().__init__(
            message=f"{message}: {rm_name}",
            status_code=503,
            details=details,
            xid=xid,
        )
        self.rm_name = rm_name


class TransactionNotFoundError(WCException):
    """Exception raised when a transaction ID is not found."""

    def __init__(
        self,
        xid: str,
        details: Optional[str] = None,
    ):
        super().__init__(
            message=f"Transaction not found: {xid}",
            status_code=404,
            details=details,
            xid=xid,
        )


class ResourceNotFoundError(WCException):
    """Exception raised when a resource is not found in RM."""

    def __init__(
        self,
        resource_type: str,
        resource_key: str,
        details: Optional[str] = None,
        xid: Optional[str] = None,
    ):
        super().__init__(
            message=f"{resource_type} not found: {resource_key}",
            status_code=404,
            details=details,
            xid=xid,
        )
        self.resource_type = resource_type
        self.resource_key = resource_key


class ResourceConflictError(WCException):
    """
    Exception raised when a resource conflict occurs (e.g., insufficient inventory).

    This error automatically triggers abort if auto_abort_on_error is enabled.
    """

    def __init__(
        self,
        resource_type: str,
        resource_key: str,
        message: str = "Resource conflict",
        details: Optional[str] = None,
        xid: Optional[str] = None,
    ):
        super().__init__(
            message=f"{resource_type} {resource_key}: {message}",
            status_code=409,
            details=details,
            xid=xid,
        )
        self.resource_type = resource_type
        self.resource_key = resource_key


class ReservationError(WCException):
    """
    Exception raised when a reservation operation fails.

    This error automatically triggers abort if auto_abort_on_error is enabled.
    """

    def __init__(
        self,
        message: str = "Reservation failed",
        details: Optional[str] = None,
        xid: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            status_code=400,
            details=details,
            xid=xid,
        )


class CommitTimeoutError(WCException):
    """
    Exception raised when commit operation times out.

    This error returns IN_DOUBT status, requiring the client to query transaction status.
    """

    def __init__(
        self,
        xid: str,
        details: Optional[str] = None,
    ):
        super().__init__(
            message="Commit operation timed out",
            status_code=200,  # Return 200 with IN_DOUBT status
            details=details or "Please query transaction status to verify final state",
            xid=xid,
        )


class AbortError(WCException):
    """Exception raised when abort operation fails."""

    def __init__(
        self,
        xid: str,
        details: Optional[str] = None,
    ):
        super().__init__(
            message=f"Failed to abort transaction: {xid}",
            status_code=500,
            details=details,
            xid=xid,
        )


class ValidationError(WCException):
    """Exception raised for request validation errors."""

    def __init__(
        self,
        message: str = "Validation error",
        details: Optional[str] = None,
        xid: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            status_code=400,
            details=details,
            xid=xid,
        )


class ServiceUnavailableError(WCException):
    """
    Exception raised when WC service is intentionally unavailable (e.g., after die()).

    This is used by the /admin/die endpoint.
    """

    def __init__(
        self,
        message: str = "Service is unavailable",
        details: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            status_code=503,
            details=details,
        )
