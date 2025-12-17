"""
Reservation Orchestrator

This module handles cross-RM reservation logic, coordinating inventory
deduction and reservation record creation as an atomic operation.
"""

import logging
from typing import Dict, Any

from src.wc.services.rm_client import RMClient
from src.wc.services.tm_client import TMClient
from src.wc.models import ReservationType
from src.wc.exceptions import ReservationError
from src.wc.config import get_config

logger = logging.getLogger(__name__)


class ReservationOrchestrator:
    """
    Orchestrator for cross-RM reservation operations.

    A reservation requires two atomic steps within the same transaction:
    1. Deduct inventory from the resource RM (Flights/Hotels/Cars)
    2. Add reservation record to Customers RM

    Both steps must succeed or the transaction will be aborted.

    Example Flow:
        1. Client: POST /flights/CA1234/reservations {"custName": "Alice"}
        2. WC calls orchestrator.reserve_flight("tx_001", "CA1234", "Alice")
        3. Orchestrator:
           a. flights_rm.reserve("tx_001", "CA1234", quantity=1)
           b. customers_rm.add_reservation("tx_001", {
                 "custName": "Alice",
                 "resvType": "FLIGHT",
                 "resvKey": "CA1234"
              })
        4. If both succeed, return success; if either fails, exception is raised
           and auto-abort mechanism will trigger
    """

    def __init__(
        self,
        flights_rm: RMClient,
        hotels_rm: RMClient,
        cars_rm: RMClient,
        customers_rm: RMClient,
        tm_client: TMClient,
    ):
        """
        Initialize reservation orchestrator.

        Args:
            flights_rm: Flights RM client
            hotels_rm: Hotels RM client
            cars_rm: Cars RM client
            customers_rm: Customers RM client
            tm_client: TM client (for auto-abort)
        """
        self.flights_rm = flights_rm
        self.hotels_rm = hotels_rm
        self.cars_rm = cars_rm
        self.customers_rm = customers_rm
        self.tm_client = tm_client
        self.config = get_config()

    async def reserve_flight(
        self,
        xid: str,
        flight_num: str,
        cust_name: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """
        Reserve a flight for a customer.

        This is a two-step atomic operation:
        1. Reserve inventory from Flights RM
        2. Add reservation record to Customers RM

        Args:
            xid: Transaction ID
            flight_num: Flight number
            cust_name: Customer name
            quantity: Number of seats to reserve

        Returns:
            Reservation result

        Raises:
            ReservationError: If reservation fails
            ResourceConflictError: If insufficient inventory
            RMCommunicationError: If RM communication fails

        Note:
            If any step fails and auto_abort_on_error is enabled,
            the transaction will be automatically aborted.
        """
        logger.info(
            f"Starting flight reservation: {flight_num} for {cust_name}",
            extra={"xid": xid, "flight_num": flight_num, "cust_name": cust_name}
        )

        try:
            # Step 1: Reserve inventory from Flights RM
            logger.info(
                f"Step 1: Reserving flight inventory: {flight_num}",
                extra={"xid": xid, "flight_num": flight_num, "quantity": quantity}
            )
            reserve_result = await self.flights_rm.reserve(xid, flight_num, quantity)

            # Step 2: Add reservation record to Customers RM
            logger.info(
                f"Step 2: Adding reservation record for {cust_name}",
                extra={"xid": xid, "cust_name": cust_name, "flight_num": flight_num}
            )
            await self.customers_rm.add_reservation(
                xid,
                {
                    "custName": cust_name,
                    "resvType": ReservationType.FLIGHT.value,
                    "resvKey": flight_num,
                }
            )

            logger.info(
                f"Flight reservation completed: {flight_num} for {cust_name}",
                extra={"xid": xid, "flight_num": flight_num, "cust_name": cust_name}
            )

            return {
                "success": True,
                "message": "Flight reserved successfully",
                "numAvail": reserve_result.get("numAvail"),
            }

        except Exception as e:
            logger.error(
                f"Flight reservation failed: {str(e)}",
                extra={"xid": xid, "flight_num": flight_num, "cust_name": cust_name},
                exc_info=True
            )

            # Auto-abort if enabled
            if self.config.auto_abort_on_error:
                logger.warning(f"Auto-aborting transaction: {xid}")
                try:
                    await self.tm_client.abort(xid)
                except Exception as abort_error:
                    logger.error(
                        f"Auto-abort failed: {str(abort_error)}",
                        extra={"xid": xid},
                        exc_info=True
                    )

            # Re-raise the original exception
            raise

    async def reserve_hotel(
        self,
        xid: str,
        location: str,
        cust_name: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """
        Reserve a hotel for a customer.

        This is a two-step atomic operation:
        1. Reserve inventory from Hotels RM
        2. Add reservation record to Customers RM

        Args:
            xid: Transaction ID
            location: Hotel location
            cust_name: Customer name
            quantity: Number of rooms to reserve

        Returns:
            Reservation result

        Raises:
            ReservationError: If reservation fails
            ResourceConflictError: If insufficient inventory
            RMCommunicationError: If RM communication fails
        """
        logger.info(
            f"Starting hotel reservation: {location} for {cust_name}",
            extra={"xid": xid, "location": location, "cust_name": cust_name}
        )

        try:
            # Step 1: Reserve inventory from Hotels RM
            logger.info(
                f"Step 1: Reserving hotel inventory: {location}",
                extra={"xid": xid, "location": location, "quantity": quantity}
            )
            reserve_result = await self.hotels_rm.reserve(xid, location, quantity)

            # Step 2: Add reservation record to Customers RM
            logger.info(
                f"Step 2: Adding reservation record for {cust_name}",
                extra={"xid": xid, "cust_name": cust_name, "location": location}
            )
            await self.customers_rm.add_reservation(
                xid,
                {
                    "custName": cust_name,
                    "resvType": ReservationType.HOTEL.value,
                    "resvKey": location,
                }
            )

            logger.info(
                f"Hotel reservation completed: {location} for {cust_name}",
                extra={"xid": xid, "location": location, "cust_name": cust_name}
            )

            return {
                "success": True,
                "message": "Hotel reserved successfully",
                "numAvail": reserve_result.get("numAvail"),
            }

        except Exception as e:
            logger.error(
                f"Hotel reservation failed: {str(e)}",
                extra={"xid": xid, "location": location, "cust_name": cust_name},
                exc_info=True
            )

            # Auto-abort if enabled
            if self.config.auto_abort_on_error:
                logger.warning(f"Auto-aborting transaction: {xid}")
                try:
                    await self.tm_client.abort(xid)
                except Exception as abort_error:
                    logger.error(
                        f"Auto-abort failed: {str(abort_error)}",
                        extra={"xid": xid},
                        exc_info=True
                    )

            # Re-raise the original exception
            raise

    async def reserve_car(
        self,
        xid: str,
        location: str,
        cust_name: str,
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """
        Reserve a car for a customer.

        This is a two-step atomic operation:
        1. Reserve inventory from Cars RM
        2. Add reservation record to Customers RM

        Args:
            xid: Transaction ID
            location: Car rental location
            cust_name: Customer name
            quantity: Number of cars to reserve

        Returns:
            Reservation result

        Raises:
            ReservationError: If reservation fails
            ResourceConflictError: If insufficient inventory
            RMCommunicationError: If RM communication fails
        """
        logger.info(
            f"Starting car reservation: {location} for {cust_name}",
            extra={"xid": xid, "location": location, "cust_name": cust_name}
        )

        try:
            # Step 1: Reserve inventory from Cars RM
            logger.info(
                f"Step 1: Reserving car inventory: {location}",
                extra={"xid": xid, "location": location, "quantity": quantity}
            )
            reserve_result = await self.cars_rm.reserve(xid, location, quantity)

            # Step 2: Add reservation record to Customers RM
            logger.info(
                f"Step 2: Adding reservation record for {cust_name}",
                extra={"xid": xid, "cust_name": cust_name, "location": location}
            )
            await self.customers_rm.add_reservation(
                xid,
                {
                    "custName": cust_name,
                    "resvType": ReservationType.CAR.value,
                    "resvKey": location,
                }
            )

            logger.info(
                f"Car reservation completed: {location} for {cust_name}",
                extra={"xid": xid, "location": location, "cust_name": cust_name}
            )

            return {
                "success": True,
                "message": "Car reserved successfully",
                "numAvail": reserve_result.get("numAvail"),
            }

        except Exception as e:
            logger.error(
                f"Car reservation failed: {str(e)}",
                extra={"xid": xid, "location": location, "cust_name": cust_name},
                exc_info=True
            )

            # Auto-abort if enabled
            if self.config.auto_abort_on_error:
                logger.warning(f"Auto-aborting transaction: {xid}")
                try:
                    await self.tm_client.abort(xid)
                except Exception as abort_error:
                    logger.error(
                        f"Auto-abort failed: {str(abort_error)}",
                        extra={"xid": xid},
                        exc_info=True
                    )

            # Re-raise the original exception
            raise
