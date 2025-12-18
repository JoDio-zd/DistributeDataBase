import threading

class RowLockManager:
    def __init__(self):
        # key -> xid
        self._locks = {}
        self._mutex = threading.Lock()

    def try_lock(self, key: str, xid: int) -> bool:
        with self._mutex:
            owner = self._locks.get(key)
            if owner is None:
                self._locks[key] = xid
                return True
            if owner == xid:
                # already locked by self (idempotent)
                return True
            return False
    
    def unlock_all(self, xid: int) -> None:
        with self._mutex:
            to_release = [k for k, v in self._locks.items() if v == xid]
            for k in to_release:
                del self._locks[k]

