"""
Hotels API Router

Handles CRUD operations and reservations for hotels.
"""

from fastapi import APIRouter, Depends, Request
from src.wc.models import (
    HotelCreate, HotelUpdate, HotelResponse, ReserveRequest, ReserveResponse
)
from src.wc.services.rm_client import RMClient
from src.wc.services.orchestrator import ReservationOrchestrator
from src.wc.services.tm_client import TMClient
from src.wc.middleware import get_transaction_id
from src.wc.utils import auto_abort_on_error
import src.wc.main as main_module

router = APIRouter()


@router.post("/hotels", response_model=HotelResponse, status_code=201)
async def create_hotel(
    hotel: HotelCreate,
    request: Request,
    hotels_rm: RMClient = Depends(main_module.get_hotels_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Create a new hotel."""
    xid = get_transaction_id(request)
    try:
        result = await hotels_rm.add(xid, hotel.dict())
        return HotelResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.get("/hotels/{location}", response_model=HotelResponse)
async def get_hotel(
    location: str,
    request: Request,
    hotels_rm: RMClient = Depends(main_module.get_hotels_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Query a hotel by location."""
    xid = get_transaction_id(request)
    try:
        result = await hotels_rm.query(location, xid)
        return HotelResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.patch("/hotels/{location}", response_model=HotelResponse)
async def update_hotel(
    location: str,
    hotel: HotelUpdate,
    request: Request,
    hotels_rm: RMClient = Depends(main_module.get_hotels_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Update a hotel (partial update)."""
    xid = get_transaction_id(request)
    update_data = hotel.dict(exclude_unset=True)
    try:
        result = await hotels_rm.update(xid, location, update_data)
        return HotelResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.delete("/hotels/{location}", status_code=204)
async def delete_hotel(
    location: str,
    request: Request,
    hotels_rm: RMClient = Depends(main_module.get_hotels_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Delete a hotel."""
    xid = get_transaction_id(request)
    try:
        await hotels_rm.delete(xid, location)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.post("/hotels/{location}/reservations", response_model=ReserveResponse, status_code=201)
async def reserve_hotel(
    location: str,
    reserve_req: ReserveRequest,
    request: Request,
    orchestrator: ReservationOrchestrator = Depends(main_module.get_orchestrator),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """
    Reserve a hotel room for a customer.

    This is a cross-RM operation that:
    1. Decrements available rooms in Hotels RM
    2. Adds a reservation record in Customers RM
    """
    xid = get_transaction_id(request)
    try:
        result = await orchestrator.reserve_hotel(
            xid=xid,
            location=location,
            cust_name=reserve_req.custName,
            quantity=reserve_req.quantity
        )
        return ReserveResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise
