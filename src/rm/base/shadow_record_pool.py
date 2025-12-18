from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from src.rm.base.page import Record


class ShadowRecordPool(ABC):
    """
    Transaction-local write set.

    Stores private (uncommitted) modifications at record (key) granularity.
    """

    @abstractmethod
    def has_record(self, xid: int, key: str) -> bool:
        """Whether the transaction has modified this key."""
        pass

    @abstractmethod
    def get_record(self, xid: int, key: str) -> Optional[Record]:
        """
        Get the shadow record for a key.
        Returns None if the key is marked as deleted.
        """
        pass

    @abstractmethod
    def put_record(self, xid: int, key: str, record: Dict[str, Any]) -> None:
        """
        Insert or update a record in the transaction's private workspace.
        """
        pass

    @abstractmethod
    def delete_record(self, xid: int, key: str) -> None:
        """
        Mark a key as deleted in the transaction's private workspace.
        """
        pass

    @abstractmethod
    def get_records(self, xid: int) -> Dict[str, Dict[str, Any]]:
        """
        Return all modified keys for the transaction.
        Used during prepare/commit.
        """
        pass

    @abstractmethod
    def remove_txn(self, xid: int) -> None:
        """Discard all private state for a transaction."""
        pass
