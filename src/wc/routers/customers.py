"""
Customers API Router

Handles CRUD operations for customers and reservation queries.
"""

from fastapi import APIRouter, Depends, Request
from src.wc.models import (
    CustomerCreate, CustomerResponse, CustomerReservationsResponse
)
from src.wc.services.rm_client import RMClient
from src.wc.services.tm_client import TMClient
from src.wc.middleware import get_transaction_id
from src.wc.utils import auto_abort_on_error
import src.wc.main as main_module

router = APIRouter()


@router.post("/customers", response_model=CustomerResponse, status_code=201)
async def create_customer(
    customer: CustomerCreate,
    request: Request,
    customers_rm: RMClient = Depends(main_module.get_customers_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Create a new customer."""
    xid = get_transaction_id(request)
    try:
        result = await customers_rm.add(xid, customer.dict())
        return CustomerResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.get("/customers/{custName}", response_model=CustomerResponse)
async def get_customer(
    custName: str,
    request: Request,
    customers_rm: RMClient = Depends(main_module.get_customers_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """Query a customer by name."""
    xid = get_transaction_id(request)
    try:
        result = await customers_rm.query(custName, xid)
        return CustomerResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.delete("/customers/{custName}", status_code=204)
async def delete_customer(
    custName: str,
    request: Request,
    customers_rm: RMClient = Depends(main_module.get_customers_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """
    Delete a customer.

    This will also cascade delete all their reservations.
    """
    xid = get_transaction_id(request)
    try:
        await customers_rm.delete(xid, custName)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise


@router.get("/customers/{custName}/reservations", response_model=CustomerReservationsResponse)
async def get_customer_reservations(
    custName: str,
    request: Request,
    customers_rm: RMClient = Depends(main_module.get_customers_rm),
    tm_client: TMClient = Depends(main_module.get_tm_client),
):
    """
    Get all reservations for a customer.

    Returns all flights, hotels, and car reservations.
    """
    xid = get_transaction_id(request)
    try:
        result = await customers_rm.get_customer_reservations(custName, xid)
        return CustomerReservationsResponse(**result)
    except Exception as exc:
        await auto_abort_on_error(xid, tm_client, exc)
        raise
