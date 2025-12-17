"""
TM (Transaction Manager) Client

This module provides a client for communicating with the Transaction Manager.
According to the API contract specification, TM provides the following endpoints:
- POST /transactions - Create a new transaction
- POST /transactions/{xid}/commit - Commit a transaction
- POST /transactions/{xid}/abort - Abort a transaction
- GET /transactions/{xid} - Query transaction status
"""

import logging
from typing import Optional
import httpx

from src.wc.models import TransactionStatus
from src.wc.exceptions import TMCommunicationError

logger = logging.getLogger(__name__)


class TMClient:
    """
    Client for Transaction Manager communication.

    This client handles all HTTP communication with the TM service,
    including error handling, retries, and logging.

    **Expected TM Interface** (see docs/API_CONTRACTS.md for full specification):

    1. POST /transactions
       Response: {"xid": "tx_xxx", "status": "ACTIVE"}

    2. POST /transactions/{xid}/commit
       Response: {"xid": "tx_xxx", "status": "COMMITTED|IN_DOUBT"}

    3. POST /transactions/{xid}/abort
       Response: {"xid": "tx_xxx", "status": "ABORTED"}

    4. GET /transactions/{xid}
       Response: {"xid": "tx_xxx", "status": "ACTIVE|PREPARING|COMMITTED|ABORTED|IN_DOUBT"}
    """

    def __init__(self, base_url: str, http_client: httpx.AsyncClient):
        """
        Initialize TM client.

        Args:
            base_url: Base URL of the TM service (e.g., http://localhost:8001)
            http_client: Shared httpx client for connection pooling
        """
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client

    async def start_transaction(self) -> str:
        """
        Create a new transaction and return its ID.

        Returns:
            Transaction ID (xid)

        Raises:
            TMCommunicationError: If communication with TM fails

        Example:
            >>> xid = await tm_client.start_transaction()
            >>> print(xid)  # "tx_20231217_001234"
        """
        url = f"{self.base_url}/transactions"

        logger.info("Creating new transaction via TM", extra={"tm_url": url})

        try:
            response = await self.http_client.post(url)
            response.raise_for_status()
            data = response.json()

            xid = data.get("xid")
            status = data.get("status")

            logger.info(
                f"Transaction created: {xid}",
                extra={"xid": xid, "status": status}
            )

            return xid

        except httpx.HTTPStatusError as e:
            error_msg = f"TM returned error: {e.response.status_code}"
            logger.error(error_msg, extra={"url": url, "status_code": e.response.status_code})
            raise TMCommunicationError(message=error_msg, details=str(e))

        except httpx.RequestError as e:
            error_msg = f"Failed to connect to TM: {str(e)}"
            logger.error(error_msg, extra={"url": url})
            raise TMCommunicationError(message=error_msg, details=str(e))

        except Exception as e:
            error_msg = f"Unexpected error communicating with TM: {str(e)}"
            logger.error(error_msg, extra={"url": url}, exc_info=True)
            raise TMCommunicationError(message=error_msg, details=str(e))

    async def commit(self, xid: str) -> dict:
        """
        Commit a transaction via TM (triggers 2PC).

        Args:
            xid: Transaction ID

        Returns:
            dict with "xid" and "status"

        Example:
            >>> result = await tm_client.commit("tx_001")
            >>> print(result["status"])  # "COMMITTED"
        """
        url = f"{self.base_url}/transactions/{xid}/commit"

        logger.info(f"Committing transaction: {xid}", extra={"xid": xid, "tm_url": url})

        try:
            response = await self.http_client.post(url)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")

            if status == "IN_DOUBT":
                message = data.get("message") or "Commit timed out, status uncertain"
                logger.warning(
                    f"Transaction commit timed out: {xid}",
                    extra={"xid": xid, "status": status}
                )
                return {"xid": xid, "status": TransactionStatus.IN_DOUBT.value, "message": message}

            logger.info(
                f"Transaction committed: {xid}",
                extra={"xid": xid, "status": status}
            )

            return data

        except httpx.HTTPStatusError as e:
            error_msg = f"TM commit failed: {e.response.status_code}"
            logger.error(error_msg, extra={"xid": xid, "url": url, "status_code": e.response.status_code})
            raise TMCommunicationError(message=error_msg, details=str(e), xid=xid)

        except httpx.RequestError as e:
            error_msg = f"Failed to connect to TM for commit: {str(e)}"
            logger.error(error_msg, extra={"xid": xid, "url": url})
            raise TMCommunicationError(message=error_msg, details=str(e), xid=xid)

        except Exception as e:
            error_msg = f"Unexpected error during commit: {str(e)}"
            logger.error(error_msg, extra={"xid": xid, "url": url}, exc_info=True)
            raise TMCommunicationError(message=error_msg, details=str(e), xid=xid)

    async def abort(self, xid: str) -> dict:
        """
        Abort a transaction via TM.

        Args:
            xid: Transaction ID

        Returns:
            dict with "xid" and "status"

        Raises:
            TMCommunicationError: If communication with TM fails

        Note:
            This method is idempotent - multiple calls with the same xid
            should return the same result.

        Example:
            >>> result = await tm_client.abort("tx_001")
            >>> print(result["status"])  # "ABORTED"
        """
        url = f"{self.base_url}/transactions/{xid}/abort"

        logger.info(f"Aborting transaction: {xid}", extra={"xid": xid, "tm_url": url})

        try:
            response = await self.http_client.post(url)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")

            logger.info(
                f"Transaction aborted: {xid}",
                extra={"xid": xid, "status": status}
            )

            return data

        except httpx.HTTPStatusError as e:
            error_msg = f"TM abort failed: {e.response.status_code}"
            logger.error(error_msg, extra={"xid": xid, "url": url, "status_code": e.response.status_code})
            raise TMCommunicationError(message=error_msg, details=str(e), xid=xid)

        except httpx.RequestError as e:
            error_msg = f"Failed to connect to TM for abort: {str(e)}"
            logger.error(error_msg, extra={"xid": xid, "url": url})
            raise TMCommunicationError(message=error_msg, details=str(e), xid=xid)

        except Exception as e:
            error_msg = f"Unexpected error during abort: {str(e)}"
            logger.error(error_msg, extra={"xid": xid, "url": url}, exc_info=True)
            raise TMCommunicationError(message=error_msg, details=str(e), xid=xid)

    async def get_status(self, xid: str) -> dict:
        """
        Query transaction status from TM.

        Args:
            xid: Transaction ID

        Returns:
            dict with "xid" and "status"

        Raises:
            TMCommunicationError: If communication with TM fails

        Example:
            >>> result = await tm_client.get_status("tx_001")
            >>> print(result["status"])  # "COMMITTED"
        """
        url = f"{self.base_url}/transactions/{xid}"

        logger.info(f"Querying transaction status: {xid}", extra={"xid": xid, "tm_url": url})

        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")

            logger.info(
                f"Transaction status retrieved: {xid} - {status}",
                extra={"xid": xid, "status": status}
            )

            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_msg = f"Transaction not found: {xid}"
                logger.error(error_msg, extra={"xid": xid, "url": url})
                raise TMCommunicationError(message=error_msg, details="Transaction does not exist", xid=xid)
            else:
                error_msg = f"TM status query failed: {e.response.status_code}"
                logger.error(error_msg, extra={"xid": xid, "url": url, "status_code": e.response.status_code})
                raise TMCommunicationError(message=error_msg, details=str(e), xid=xid)

        except httpx.RequestError as e:
            error_msg = f"Failed to connect to TM for status query: {str(e)}"
            logger.error(error_msg, extra={"xid": xid, "url": url})
            raise TMCommunicationError(message=error_msg, details=str(e), xid=xid)

        except Exception as e:
            error_msg = f"Unexpected error querying transaction status: {str(e)}"
            logger.error(error_msg, extra={"xid": xid, "url": url}, exc_info=True)
            raise TMCommunicationError(message=error_msg, details=str(e), xid=xid)

    async def check_health(self) -> bool:
        """
        Check if TM is reachable (used by reconnect).

        Returns:
            True if TM is healthy, False otherwise
        """
        try:
            # Try to query a dummy transaction to check connectivity
            # We expect 404, but that means TM is responding
            url = f"{self.base_url}/transactions/health_check"
            response = await self.http_client.get(url, timeout=5.0)
            # Any response (including 404) means TM is up
            return True
        except Exception as e:
            logger.warning(f"TM health check failed: {str(e)}")
            return False
