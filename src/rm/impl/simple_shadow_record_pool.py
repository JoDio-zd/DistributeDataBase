from src.rm.base.shadow_record_pool import ShadowRecordPool
import copy

class SimpleShadowRecordPool(ShadowRecordPool):
    """
    A simple in-memory shadow record pool (write-set).

    Structure:
        xid -> key -> record | None
    where None represents a deletion (tombstone).
    """

    def __init__(self):
        self._records = {}  # xid -> {key -> record | None}

    def has_record(self, xid: int, key: str) -> bool:
        return xid in self._records and key in self._records[xid]

    def get_record(self, xid: int, key: str):
        if not self.has_record(xid, key):
            return None
        return self._records[xid][key]

    def put_record(self, xid: int, key: str, record: dict) -> None:
        # deep copy to isolate transaction-local changes
        self._records.setdefault(xid, {})[key] = copy.deepcopy(record)

    def delete_record(self, xid: int, key: str) -> None:
        self._records[xid][key].deleted = True

    def get_records(self, xid: int) -> dict:
        return self._records.get(xid, {})

    def remove_txn(self, xid: int) -> None:
        self._records.pop(xid, None)
