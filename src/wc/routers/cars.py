"""
Cars API Router

Handles CRUD operations and reservations for car rentals.
"""

from fastapi import APIRouter, Depends, Request
from src.wc.models import (
    CarCreate, CarUpdate, CarResponse, ReserveRequest, ReserveResponse
)
from src.wc.services.rm_client import RMClient
from src.wc.services.orchestrator import ReservationOrchestrator
from src.wc.services.tm_client import TMClient
from src.wc.middleware import get_transaction_id
from src.wc.utils import auto_abort_on_error
import src.wc.main as main_module

router = APIRouter()


@router.post("/cars", response_model=CarResponse, status_code=201)
async def create_car(
    car: CarCreate,
    request: Request,
    cars_rm: RMClient = Depends(main_module.get_cars_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Create a new car rental."""
    xid = get_transaction_id(request)
    try:
        result = await cars_rm.add(xid, car.dict())
        return CarResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.get("/cars/{location}", response_model=CarResponse)
async def get_car(
    location: str,
    request: Request,
    cars_rm: RMClient = Depends(main_module.get_cars_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Query car rental by location."""
    xid = get_transaction_id(request)
    try:
        result = await cars_rm.query(location, xid)
        return CarResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.patch("/cars/{location}", response_model=CarResponse)
async def update_car(
    location: str,
    car: CarUpdate,
    request: Request,
    cars_rm: RMClient = Depends(main_module.get_cars_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Update a car rental (partial update)."""
    xid = get_transaction_id(request)
    update_data = car.dict(exclude_unset=True)
    try:
        result = await cars_rm.update(xid, location, update_data)
        return CarResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.delete("/cars/{location}", status_code=204)
async def delete_car(
    location: str,
    request: Request,
    cars_rm: RMClient = Depends(main_module.get_cars_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Delete a car rental."""
    xid = get_transaction_id(request)
    try:
        await cars_rm.delete(xid, location)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.post("/cars/{location}/reservations", response_model=ReserveResponse, status_code=201)
async def reserve_car(
    location: str,
    reserve_req: ReserveRequest,
    request: Request,
    orchestrator: ReservationOrchestrator = Depends(main_module.get_orchestrator),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """
    Reserve a car for a customer.

    This is a cross-RM operation that:
    1. Decrements available cars in Cars RM
    2. Adds a reservation record in Customers RM
    """
    xid = get_transaction_id(request)
    try:
        result = await orchestrator.reserve_car(
            xid=xid,
            location=location,
            cust_name=reserve_req.custName,
            quantity=reserve_req.quantity
        )
        return ReserveResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise
