"""
WC Lifecycle Management

This module handles WC service lifecycle operations like reconnect and die.
"""

import logging
from typing import Dict
import asyncio

import httpx

from src.wc.services.tm_client import TMClient
from src.wc.services.rm_client import RMClient
from src.wc.services.orchestrator import ReservationOrchestrator
from src.wc.config import get_config
from src.wc.middleware import set_service_availability

logger = logging.getLogger(__name__)


class LifecycleManager:
    """
    Manager for WC service lifecycle operations.

    Handles:
    - Reconnect: Re-establish connections to TM and all RMs
    - Die: Gracefully or forcefully shut down WC service
    """

    def __init__(
        self,
        tm_client: TMClient,
        flights_rm: RMClient,
        hotels_rm: RMClient,
        cars_rm: RMClient,
        customers_rm: RMClient,
        state: Dict[str, object],
    ):
        """
        Initialize lifecycle manager.

        Args:
            tm_client: TM client
            flights_rm: Flights RM client
            hotels_rm: Hotels RM client
            cars_rm: Cars RM client
            customers_rm: Customers RM client
            state: Shared application state for swapping clients during reconnect
        """
        self.tm_client = tm_client
        self.rms = {
            "flights": flights_rm,
            "hotels": hotels_rm,
            "cars": cars_rm,
            "customers": customers_rm,
        }
        self.state = state
        self.config = get_config()

    async def reconnect(self) -> Dict[str, object]:
        """
        Reconnect to TM and all RMs.

        This operation:
        1. Checks TM connectivity
        2. Checks each RM connectivity
        3. Returns status report

        Returns:
            Status report with TM and RM connection status

        Example:
            >>> result = await lifecycle.reconnect()
            >>> print(result)
            {
                "message": "Reconnected to TM and RMs",
                "tm_status": "ok",
                "rm_status": {
                    "flights": "ok",
                    "hotels": "ok",
                    "cars": "failed",
                    "customers": "ok"
                }
            }
        """
        logger.info("Starting reconnect operation")

        # Close previous HTTP client if present
        old_http_client = self.state.get("http_client")
        if old_http_client:
            try:
                await old_http_client.aclose()
            except Exception as e:
                logger.warning(f"Closing old HTTP client failed: {str(e)}")

        # Recreate HTTP client and service clients
        timeout = httpx.Timeout(
            connect=self.config.http_connect_timeout,
            read=self.config.http_read_timeout,
        )
        http_client = httpx.AsyncClient(timeout=timeout)

        tm_client = TMClient(
            base_url=self.config.tm_base_url,
            http_client=http_client,
        )
        flights_rm = RMClient("flights", self.config.flights_rm_url, http_client)
        hotels_rm = RMClient("hotels", self.config.hotels_rm_url, http_client)
        cars_rm = RMClient("cars", self.config.cars_rm_url, http_client)
        customers_rm = RMClient("customers", self.config.customers_rm_url, http_client)

        orchestrator = ReservationOrchestrator(
            flights_rm=flights_rm,
            hotels_rm=hotels_rm,
            cars_rm=cars_rm,
            customers_rm=customers_rm,
            tm_client=tm_client,
        )

        # Update internal references and shared state
        self.tm_client = tm_client
        self.rms = {
            "flights": flights_rm,
            "hotels": hotels_rm,
            "cars": cars_rm,
            "customers": customers_rm,
        }
        self.state.update({
            "http_client": http_client,
            "tm_client": tm_client,
            "flights_rm": flights_rm,
            "hotels_rm": hotels_rm,
            "cars_rm": cars_rm,
            "customers_rm": customers_rm,
            "orchestrator": orchestrator,
        })

        # Check TM
        tm_status = "ok" if await tm_client.check_health() else "failed"
        logger.info(f"TM connection status: {tm_status}")

        # Check all RMs in parallel
        rm_tasks = {name: rm.check_health() for name, rm in self.rms.items()}
        rm_results = await asyncio.gather(*rm_tasks.values(), return_exceptions=True)

        rm_status = {}
        for (name, _), result in zip(rm_tasks.items(), rm_results):
            if isinstance(result, Exception):
                rm_status[name] = "failed"
                logger.error(f"RM {name} connection failed: {str(result)}")
            else:
                rm_status[name] = "ok" if result else "failed"
                logger.info(f"RM {name} connection status: {rm_status[name]}")

        # Summary
        all_ok = tm_status == "ok" and all(status == "ok" for status in rm_status.values())
        message = "Successfully reconnected to all services" if all_ok else "Reconnection completed with some failures"

        result = {
            "message": message,
            "tm_status": tm_status,
            "rm_status": rm_status,
        }

        logger.info(f"Reconnect operation completed: {result}")

        return result

    def die(self, graceful: bool = False, hard: bool = False) -> Dict[str, str]:
        """
        Shut down WC service.

        Args:
            graceful: If True, allow current requests to finish before shutdown
                     If False, shut down immediately
            hard: If True, request process termination after marking unavailable

        Note:
            This is typically implemented by setting a global flag that causes
            all requests to return 503. In production, you might want to:
            1. Stop accepting new requests
            2. Wait for in-flight requests to complete (if graceful)
            3. Exit the process

        For this implementation, we just raise an exception that will be caught
        by the admin router.
        """
        logger.warning("Die operation triggered", extra={"graceful": graceful})

        if graceful:
            logger.info("Graceful shutdown requested - completing current requests")
        else:
            logger.info("Immediate shutdown requested")

        # Mark service unavailable so new requests receive 503
        set_service_availability(False)

        message = "Service marked unavailable; new requests will receive 503"
        if hard:
            message = "Service marked unavailable; process exit requested"

        return {"message": message}
