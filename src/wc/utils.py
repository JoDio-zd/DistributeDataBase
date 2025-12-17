"""
Utility helpers for the Workflow Controller.

Currently contains helper to auto-abort a transaction on errors when enabled.
"""

import logging
from typing import Optional

from src.wc.config import get_config
from src.wc.services.tm_client import TMClient

logger = logging.getLogger(__name__)


async def auto_abort_on_error(xid: Optional[str], tm_client: TMClient, exc: Exception) -> None:
    """
    Abort the given transaction if auto-abort is enabled and xid is present.

    Best-effort: errors during abort are logged but not raised.
    """
    config = get_config()
    if not config.auto_abort_on_error or not xid:
        return

    try:
        await tm_client.abort(xid)
        logger.warning(
            "Auto-aborted transaction due to error",
            extra={"xid": xid, "error": str(exc)},
        )
    except Exception as abort_error:
        logger.error(
            "Auto-abort failed",
            extra={"xid": xid, "abort_error": str(abort_error)},
        )
