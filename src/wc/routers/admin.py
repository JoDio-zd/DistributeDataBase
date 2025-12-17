"""
Admin API Router

Handles administrative operations: die and reconnect.
"""

import sys
from fastapi import APIRouter, Depends
from src.wc.models import DieResponse, ReconnectResponse
from src.wc.services.lifecycle import LifecycleManager
import src.wc.main as main_module

router = APIRouter()


@router.post("/die", response_model=DieResponse)
async def die(
    graceful: bool = False,
    hard: bool = False,
    lifecycle: LifecycleManager = Depends(main_module.get_lifecycle_manager)
):
    """
    Simulate WC service failure.

    This endpoint is used for testing fault tolerance and recovery.
    In production, this should be disabled.

    By default it marks the service unavailable (503 for new requests).
    If `hard=true` is provided, the process will exit.
    """
    result = lifecycle.die(graceful=graceful, hard=hard)

    if hard:
        # Forcefully exit the process
        sys.exit(1)

    return DieResponse(message=result["message"])


@router.post("/reconnect", response_model=ReconnectResponse)
async def reconnect(
    lifecycle: LifecycleManager = Depends(main_module.get_lifecycle_manager)
):
    """
    Reconnect to TM and all RMs.

    This endpoint:
    1. Re-establishes connections to TM
    2. Re-establishes connections to all RMs
    3. Returns connection status for each service

    Use this after:
    - WC restart
    - Network failures
    - TM/RM service restarts
    """
    result = await lifecycle.reconnect()
    return ReconnectResponse(**result)
