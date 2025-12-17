"""
RM (Resource Manager) Client

This module provides a generic client for communicating with Resource Managers.
Each RM (Flights, Hotels, Cars, Customers) follows the same interface pattern
with minor variations in data models.
"""

import logging
from typing import Optional, Dict, Any
import httpx

from src.wc.exceptions import (
    RMCommunicationError,
    ResourceNotFoundError,
    ResourceConflictError,
)

logger = logging.getLogger(__name__)


class RMClient:
    """
    Generic Resource Manager client.

    This client handles HTTP communication with any RM service, providing
    CRUD operations and reserve functionality. All requests automatically
    inject the X-Transaction-Id header for transaction context propagation.

    **Expected RM Interface** (see docs/API_CONTRACTS.md for full specification):

    1. POST /{resource} - Create resource
    2. GET /{resource}/{key} - Query resource
    3. PATCH /{resource}/{key} - Update resource
    4. DELETE /{resource}/{key} - Delete resource
    5. POST /{resource}/{key}/reserve - Reserve resource (for inventory RMs)
    6. POST /reservations - Add reservation (for Customers RM)
    7. GET /customers/{custName}/reservations - Query reservations (for Customers RM)

    All requests (except POST /{resource}) must include X-Transaction-Id header.
    """

    def __init__(
        self,
        resource_name: str,
        base_url: str,
        http_client: httpx.AsyncClient,
        resource_path: Optional[str] = None,
    ):
        """
        Initialize RM client.

        Args:
            resource_name: Name of the resource (e.g., "flights", "hotels")
            base_url: Base URL of the RM service
            http_client: Shared httpx client for connection pooling
            resource_path: Custom resource path (defaults to resource_name)
        """
        self.resource_name = resource_name
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.resource_path = resource_path or resource_name

    def _build_headers(self, xid: Optional[str] = None) -> Dict[str, str]:
        """
        Build HTTP headers with X-Transaction-Id.

        Args:
            xid: Transaction ID (optional for query operations)

        Returns:
            Dict of HTTP headers
        """
        headers = {"Content-Type": "application/json"}
        if xid:
            headers["X-Transaction-Id"] = xid
        return headers

    async def add(self, xid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add (create) a new resource.

        Args:
            xid: Transaction ID
            data: Resource data to create

        Returns:
            Created resource data

        Raises:
            RMCommunicationError: If communication fails
            ResourceConflictError: If resource already exists

        Example:
            >>> await rm.add("tx_001", {"flightNum": "CA1234", "price": 1000, ...})
        """
        url = f"{self.base_url}/{self.resource_path}"
        headers = self._build_headers(xid)

        logger.info(
            f"Creating {self.resource_name}",
            extra={"xid": xid, "rm": self.resource_name, "url": url}
        )

        try:
            response = await self.http_client.post(url, json=data, headers=headers)
            response.raise_for_status()
            result = response.json()

            logger.info(
                f"{self.resource_name.capitalize()} created",
                extra={"xid": xid, "rm": self.resource_name, "data": result}
            )

            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                raise ResourceConflictError(
                    resource_type=self.resource_name,
                    resource_key=str(data.get("flightNum") or data.get("location") or data.get("custName")),
                    message="Resource already exists",
                    xid=xid
                )
            else:
                logger.error(
                    f"RM add failed: {e.response.status_code}",
                    extra={"xid": xid, "rm": self.resource_name, "status_code": e.response.status_code}
                )
                raise RMCommunicationError(
                    rm_name=self.resource_name,
                    details=f"HTTP {e.response.status_code}",
                    xid=xid
                )

        except httpx.RequestError as e:
            logger.error(
                f"Failed to connect to RM: {str(e)}",
                extra={"xid": xid, "rm": self.resource_name, "url": url}
            )
            raise RMCommunicationError(
                rm_name=self.resource_name,
                details=str(e),
                xid=xid
            )

    async def query(self, key: str, xid: Optional[str] = None) -> Dict[str, Any]:
        """
        Query (read) a resource by key.

        Args:
            key: Resource key (e.g., flightNum, location, custName)
            xid: Transaction ID (optional - reads committed data if not provided)

        Returns:
            Resource data

        Raises:
            RMCommunicationError: If communication fails
            ResourceNotFoundError: If resource doesn't exist

        Example:
            >>> await rm.query("CA1234", xid="tx_001")
        """
        url = f"{self.base_url}/{self.resource_path}/{key}"
        headers = self._build_headers(xid)

        logger.info(
            f"Querying {self.resource_name}: {key}",
            extra={"xid": xid, "rm": self.resource_name, "key": key, "url": url}
        )

        try:
            response = await self.http_client.get(url, headers=headers)
            response.raise_for_status()
            result = response.json()

            logger.info(
                f"{self.resource_name.capitalize()} found: {key}",
                extra={"xid": xid, "rm": self.resource_name, "key": key}
            )

            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ResourceNotFoundError(
                    resource_type=self.resource_name,
                    resource_key=key,
                    xid=xid
                )
            else:
                logger.error(
                    f"RM query failed: {e.response.status_code}",
                    extra={"xid": xid, "rm": self.resource_name, "key": key, "status_code": e.response.status_code}
                )
                raise RMCommunicationError(
                    rm_name=self.resource_name,
                    details=f"HTTP {e.response.status_code}",
                    xid=xid
                )

        except httpx.RequestError as e:
            logger.error(
                f"Failed to connect to RM: {str(e)}",
                extra={"xid": xid, "rm": self.resource_name, "url": url}
            )
            raise RMCommunicationError(
                rm_name=self.resource_name,
                details=str(e),
                xid=xid
            )

    async def update(self, xid: str, key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a resource (partial update).

        Args:
            xid: Transaction ID
            key: Resource key
            data: Fields to update

        Returns:
            Updated resource data

        Raises:
            RMCommunicationError: If communication fails
            ResourceNotFoundError: If resource doesn't exist

        Example:
            >>> await rm.update("tx_001", "CA1234", {"price": 1200})
        """
        url = f"{self.base_url}/{self.resource_path}/{key}"
        headers = self._build_headers(xid)

        logger.info(
            f"Updating {self.resource_name}: {key}",
            extra={"xid": xid, "rm": self.resource_name, "key": key, "url": url}
        )

        try:
            response = await self.http_client.patch(url, json=data, headers=headers)
            response.raise_for_status()
            result = response.json()

            logger.info(
                f"{self.resource_name.capitalize()} updated: {key}",
                extra={"xid": xid, "rm": self.resource_name, "key": key}
            )

            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ResourceNotFoundError(
                    resource_type=self.resource_name,
                    resource_key=key,
                    xid=xid
                )
            else:
                logger.error(
                    f"RM update failed: {e.response.status_code}",
                    extra={"xid": xid, "rm": self.resource_name, "key": key, "status_code": e.response.status_code}
                )
                raise RMCommunicationError(
                    rm_name=self.resource_name,
                    details=f"HTTP {e.response.status_code}",
                    xid=xid
                )

        except httpx.RequestError as e:
            logger.error(
                f"Failed to connect to RM: {str(e)}",
                extra={"xid": xid, "rm": self.resource_name, "url": url}
            )
            raise RMCommunicationError(
                rm_name=self.resource_name,
                details=str(e),
                xid=xid
            )

    async def delete(self, xid: str, key: str) -> None:
        """
        Delete a resource.

        Args:
            xid: Transaction ID
            key: Resource key

        Raises:
            RMCommunicationError: If communication fails
            ResourceNotFoundError: If resource doesn't exist

        Note:
            Deletion is transactional - takes effect only after commit.

        Example:
            >>> await rm.delete("tx_001", "CA1234")
        """
        url = f"{self.base_url}/{self.resource_path}/{key}"
        headers = self._build_headers(xid)

        logger.info(
            f"Deleting {self.resource_name}: {key}",
            extra={"xid": xid, "rm": self.resource_name, "key": key, "url": url}
        )

        try:
            response = await self.http_client.delete(url, headers=headers)
            response.raise_for_status()

            logger.info(
                f"{self.resource_name.capitalize()} deleted: {key}",
                extra={"xid": xid, "rm": self.resource_name, "key": key}
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ResourceNotFoundError(
                    resource_type=self.resource_name,
                    resource_key=key,
                    xid=xid
                )
            else:
                logger.error(
                    f"RM delete failed: {e.response.status_code}",
                    extra={"xid": xid, "rm": self.resource_name, "key": key, "status_code": e.response.status_code}
                )
                raise RMCommunicationError(
                    rm_name=self.resource_name,
                    details=f"HTTP {e.response.status_code}",
                    xid=xid
                )

        except httpx.RequestError as e:
            logger.error(
                f"Failed to connect to RM: {str(e)}",
                extra={"xid": xid, "rm": self.resource_name, "url": url}
            )
            raise RMCommunicationError(
                rm_name=self.resource_name,
                details=str(e),
                xid=xid
            )

    async def reserve(self, xid: str, key: str, quantity: int = 1) -> Dict[str, Any]:
        """
        Reserve inventory (for Flights/Hotels/Cars RMs).

        Args:
            xid: Transaction ID
            key: Resource key (flightNum or location)
            quantity: Quantity to reserve

        Returns:
            Reserve result with numAvail

        Raises:
            RMCommunicationError: If communication fails
            ResourceConflictError: If insufficient inventory

        Example:
            >>> await rm.reserve("tx_001", "CA1234", quantity=1)
        """
        url = f"{self.base_url}/{self.resource_path}/{key}/reserve"
        headers = self._build_headers(xid)
        data = {"quantity": quantity}

        logger.info(
            f"Reserving {self.resource_name}: {key} (quantity={quantity})",
            extra={"xid": xid, "rm": self.resource_name, "key": key, "quantity": quantity}
        )

        try:
            response = await self.http_client.post(url, json=data, headers=headers)
            response.raise_for_status()
            result = response.json()

            logger.info(
                f"{self.resource_name.capitalize()} reserved: {key}",
                extra={"xid": xid, "rm": self.resource_name, "key": key, "num_avail": result.get("numAvail")}
            )

            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                raise ResourceConflictError(
                    resource_type=self.resource_name,
                    resource_key=key,
                    message="Insufficient inventory",
                    details=f"Cannot reserve {quantity} units",
                    xid=xid
                )
            else:
                logger.error(
                    f"RM reserve failed: {e.response.status_code}",
                    extra={"xid": xid, "rm": self.resource_name, "key": key, "status_code": e.response.status_code}
                )
                raise RMCommunicationError(
                    rm_name=self.resource_name,
                    details=f"HTTP {e.response.status_code}",
                    xid=xid
                )

        except httpx.RequestError as e:
            logger.error(
                f"Failed to connect to RM: {str(e)}",
                extra={"xid": xid, "rm": self.resource_name, "url": url}
            )
            raise RMCommunicationError(
                rm_name=self.resource_name,
                details=str(e),
                xid=xid
            )

    async def add_reservation(self, xid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a reservation record (for Customers RM only).

        Args:
            xid: Transaction ID
            data: Reservation data (custName, resvType, resvKey)

        Returns:
            Created reservation

        Raises:
            RMCommunicationError: If communication fails

        Example:
            >>> await customers_rm.add_reservation("tx_001", {
            ...     "custName": "Alice",
            ...     "resvType": "FLIGHT",
            ...     "resvKey": "CA1234"
            ... })
        """
        url = f"{self.base_url}/reservations"
        headers = self._build_headers(xid)

        logger.info(
            f"Adding reservation: {data}",
            extra={"xid": xid, "rm": self.resource_name, "data": data}
        )

        try:
            response = await self.http_client.post(url, json=data, headers=headers)
            response.raise_for_status()
            result = response.json()

            logger.info(
                "Reservation added",
                extra={"xid": xid, "rm": self.resource_name, "data": result}
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Add reservation failed: {e.response.status_code}",
                extra={"xid": xid, "rm": self.resource_name, "status_code": e.response.status_code}
            )
            raise RMCommunicationError(
                rm_name=self.resource_name,
                details=f"HTTP {e.response.status_code}",
                xid=xid
            )

        except httpx.RequestError as e:
            logger.error(
                f"Failed to connect to RM: {str(e)}",
                extra={"xid": xid, "rm": self.resource_name, "url": url}
            )
            raise RMCommunicationError(
                rm_name=self.resource_name,
                details=str(e),
                xid=xid
            )

    async def get_customer_reservations(self, cust_name: str, xid: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all reservations for a customer (for Customers RM only).

        Args:
            cust_name: Customer name
            xid: Transaction ID (optional)

        Returns:
            Customer reservations

        Raises:
            RMCommunicationError: If communication fails

        Example:
            >>> await customers_rm.get_customer_reservations("Alice", xid="tx_001")
        """
        url = f"{self.base_url}/customers/{cust_name}/reservations"
        headers = self._build_headers(xid)

        logger.info(
            f"Querying reservations for customer: {cust_name}",
            extra={"xid": xid, "rm": self.resource_name, "cust_name": cust_name}
        )

        try:
            response = await self.http_client.get(url, headers=headers)
            response.raise_for_status()
            result = response.json()

            logger.info(
                f"Reservations retrieved for: {cust_name}",
                extra={"xid": xid, "rm": self.resource_name, "cust_name": cust_name}
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Get reservations failed: {e.response.status_code}",
                extra={"xid": xid, "rm": self.resource_name, "status_code": e.response.status_code}
            )
            raise RMCommunicationError(
                rm_name=self.resource_name,
                details=f"HTTP {e.response.status_code}",
                xid=xid
            )

        except httpx.RequestError as e:
            logger.error(
                f"Failed to connect to RM: {str(e)}",
                extra={"xid": xid, "rm": self.resource_name, "url": url}
            )
            raise RMCommunicationError(
                rm_name=self.resource_name,
                details=str(e),
                xid=xid
            )

    async def check_health(self) -> bool:
        """
        Check if RM is reachable (used by reconnect).

        Returns:
            True if RM is healthy, False otherwise
        """
        try:
            # Try to query root endpoint
            url = f"{self.base_url}/"
            response = await self.http_client.get(url, timeout=5.0)
            return response.status_code < 500
        except Exception as e:
            logger.warning(f"RM {self.resource_name} health check failed: {str(e)}")
            return False
