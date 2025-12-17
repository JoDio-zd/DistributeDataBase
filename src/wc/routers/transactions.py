"""
Transaction API Router

Handles transaction lifecycle operations: start, commit, abort, and query status.
"""

from fastapi import APIRouter, Depends, Request
from src.wc.models import TransactionResponse
from src.wc.services.tm_client import TMClient
import src.wc.main as main_module

router = APIRouter()


@router.post("/transactions", response_model=TransactionResponse, status_code=201)
async def start_transaction(
    tm_client: TMClient = Depends(main_module.get_tm_client)
):
    """
    Start a new transaction.

    Returns the transaction ID (xid) which must be included in all
    subsequent operations as X-Transaction-Id header.
    """
    xid = await tm_client.start_transaction()
    return TransactionResponse(xid=xid, status="ACTIVE")


@router.post("/transactions/{xid}/commit", response_model=TransactionResponse)
async def commit_transaction(
    xid: str,
    tm_client: TMClient = Depends(main_module.get_tm_client)
):
    """
    Commit a transaction.

    This triggers the Two-Phase Commit protocol coordinated by the TM.
    """
    result = await tm_client.commit(xid)
    return TransactionResponse(**result)


@router.post("/transactions/{xid}/abort", response_model=TransactionResponse)
async def abort_transaction(
    xid: str,
    tm_client: TMClient = Depends(main_module.get_tm_client)
):
    """
    Abort (rollback) a transaction.

    All uncommitted changes will be discarded.
    """
    result = await tm_client.abort(xid)
    return TransactionResponse(**result)


@router.get("/transactions/{xid}", response_model=TransactionResponse)
async def get_transaction_status(
    xid: str,
    tm_client: TMClient = Depends(main_module.get_tm_client)
):
    """
    Query transaction status.

    Used to check final status after commit timeout or for debugging.
    """
    result = await tm_client.get_status(xid)
    return TransactionResponse(**result)
