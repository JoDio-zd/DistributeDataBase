"""
Flights API Router

Handles CRUD operations and reservations for flights.
"""

from fastapi import APIRouter, Depends, Request, status
from src.wc.models import (
    FlightCreate, FlightUpdate, FlightResponse, ReserveRequest, ReserveResponse
)
from src.wc.services.rm_client import RMClient
from src.wc.services.orchestrator import ReservationOrchestrator
from src.wc.services.tm_client import TMClient
from src.wc.middleware import get_transaction_id
from src.wc.utils import auto_abort_on_error
import src.wc.main as main_module

router = APIRouter()


@router.post("/flights", response_model=FlightResponse, status_code=201)
async def create_flight(
    flight: FlightCreate,
    request: Request,
    flights_rm: RMClient = Depends(main_module.get_flights_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Create a new flight."""
    xid = get_transaction_id(request)
    try:
        result = await flights_rm.add(xid, flight.dict())
        return FlightResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.get("/flights/{flightNum}", response_model=FlightResponse)
async def get_flight(
    flightNum: str,
    request: Request,
    flights_rm: RMClient = Depends(main_module.get_flights_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Query a flight by flight number."""
    xid = get_transaction_id(request)
    try:
        result = await flights_rm.query(flightNum, xid)
        return FlightResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.patch("/flights/{flightNum}", response_model=FlightResponse)
async def update_flight(
    flightNum: str,
    flight: FlightUpdate,
    request: Request,
    flights_rm: RMClient = Depends(main_module.get_flights_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Update a flight (partial update)."""
    xid = get_transaction_id(request)
    update_data = flight.dict(exclude_unset=True)
    try:
        result = await flights_rm.update(xid, flightNum, update_data)
        return FlightResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.delete("/flights/{flightNum}", status_code=204)
async def delete_flight(
    flightNum: str,
    request: Request,
    flights_rm: RMClient = Depends(main_module.get_flights_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Delete a flight."""
    xid = get_transaction_id(request)
    try:
        await flights_rm.delete(xid, flightNum)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.post("/flights/{flightNum}/reservations", response_model=ReserveResponse, status_code=201)
async def reserve_flight(
    flightNum: str,
    reserve_req: ReserveRequest,
    request: Request,
    orchestrator: ReservationOrchestrator = Depends(main_module.get_orchestrator),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """
    Reserve a flight for a customer.

    This is a cross-RM operation that:
    1. Decrements available seats in Flights RM
    2. Adds a reservation record in Customers RM
    """
    xid = get_transaction_id(request)
    try:
        result = await orchestrator.reserve_flight(
            xid=xid,
            flight_num=flightNum,
            cust_name=reserve_req.custName,
            quantity=reserve_req.quantity
        )
        return ReserveResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise
