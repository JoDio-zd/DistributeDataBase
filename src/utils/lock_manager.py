from typing import Dict, Set


class LockManager:
    """
    行级锁管理器：支持共享锁(S)与排他锁(X)
    Strict 2PL：所有锁在 commit/abort 时统一释放
    """

    def __init__(self):
        # { key: set(xid) }
        self.read_locks: Dict[str, Set[str]] = {}

        # { key: xid }
        self.write_locks: Dict[str, str] = {}

    # =======================
    # ✅ 共享锁 (S-lock)
    # =======================
    def acquire_s_lock(self, xid: str, key: str) -> bool:
        # 有别人的写锁，则冲突
        if key in self.write_locks and self.write_locks[key] != xid:
            return False

        # 加锁
        self.read_locks.setdefault(key, set()).add(xid)
        return True

    # =======================
    # ✅ 排他锁 (X-lock)
    # =======================
    def acquire_x_lock(self, xid: str, key: str) -> bool:
        # 被别人读锁占用
        if key in self.read_locks and xid not in self.read_locks[key]:
            return False

        # 被别人写锁占用
        if key in self.write_locks and self.write_locks[key] != xid:
            return False

        # ✅ 可升级 shared → exclusive
        self.write_locks[key] = xid
        return True

    # =======================
    # ✅ 释放锁（commit/abort）
    # =======================
    def release_locks(self, xid: str):
        # 清读锁
        for key in list(self.read_locks.keys()):
            if xid in self.read_locks[key]:
                self.read_locks[key].remove(xid)
                if not self.read_locks[key]:
                    del self.read_locks[key]

        # 清写锁
        for key, owner in list(self.write_locks.items()):
            if owner == xid:
                del self.write_locks[key]
