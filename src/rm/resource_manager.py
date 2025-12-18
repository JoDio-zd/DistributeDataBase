from src.rm.impl.mysql_page_io import MySQLPageIO
from src.rm.impl.committed_page_pool import CommittedPagePool
from src.rm.impl.simple_shadow_record_pool import SimpleShadowRecordPool
from src.rm.impl.order_string_page_index import OrderedStringPageIndex
from src.rm.base.page import Record
from src.rm.impl.lock_manager import RowLockManager

class ResourceManager:

    def __init__(
        self,
        *,
        db_conn,
        table: str,
        key_column: str,
        page_size: int = 2,
        key_width: int = 4,
    ):
        # Publicly invisible configuration
        self.table = table
        self.key_field = key_column
        self.key_width = key_width

        # Internal components (implementation details)
        # These are intentionally hidden from RM users.
        self.page_index = OrderedStringPageIndex(page_size, key_width)
        self.page_io = MySQLPageIO(
            conn=db_conn,
            table=table,
            key_column=key_column,
            page_index=self.page_index,
        )

        self.committed_pool = CommittedPagePool()
        self.shadow_pool = SimpleShadowRecordPool()
        self.global_last_commit_xid = 0
        self.txn_start_xid: dict[int, dict[str, int]] = {}
        self.locker = RowLockManager()

    # =========================================================
    # Internal helper methods
    # =========================================================

    def _get_record(self, xid: int, key: str, for_write: bool):
        page_id = self.page_index.record_to_page(key)
        shadow = self.shadow_pool.get_record(xid, key)
        record = None
        if shadow is not None:
            print("Read from shadow record.")
            record = shadow
        else:
            page = self.committed_pool.get_page(page_id)
            if page is None:
                page = self.page_io.page_in(page_id)
                self.committed_pool.put_page(page_id, page)
                print("Committed page loaded from DB.")
            record = page.get(key)
        if for_write:
            if shadow is None:
                self.shadow_pool.put_record(xid, key, record or {})
                print("Shadow record created for txn.")
        if xid not in self.txn_start_xid:
            self.txn_start_xid[xid] = {}
            self.txn_start_xid[xid][key] = record.version
        elif xid in self.txn_start_xid and key not in self.txn_start_xid[xid]:
            self.txn_start_xid[xid][key] = record.version
        return record

    def read(self, xid: int, key):
        key = key.zfill(self.key_width)
        record = self._get_record(xid, key, for_write=False)
        return record

    def upsert(self, xid: int, record: dict) -> None:
        # For Insert operation, we assume the record contains the key field.
        key = record[self.key_field].zfill(self.key_width)
        record = Record(record, version=xid)
        self.shadow_pool.put_record(xid, key, record)

    def delete(self, xid: int, key) -> None:
        key = key.zfill(self.key_width)
        record = self._get_record(xid, key, for_write=True)
        record.deleted = True
        record.version = xid

    # =========================================================
    # Transaction control (used by TM)
    # =========================================================

    def prepare(self, xid: int) -> bool:
        shadow = self.shadow_pool.get_records(xid)
        keys = sorted(k.zfill(self.key_width) for k in shadow.keys())
        for key in keys:
            if not self.locker.try_lock(key, xid):
                self.locker.unlock_all(xid)
                return False
        for key in keys:
            page_id = self.page_index.record_to_page(key)
            current_version = self.committed_pool.get_record_version(page_id, key)
            if key not in self.txn_start_xid[xid]:
                continue
            start_version = self.txn_start_xid[xid][key]
            if current_version is None:
                self.locker.unlock_all(xid)
                return False
            if current_version != start_version:
                self.locker.unlock_all(xid)
                return False
        return True

    def commit(self, xid: int) -> None:
        shadow = self.shadow_pool.get_records(xid)
        keys = sorted(k.zfill(self.key_width) for k in shadow.keys())
        for key in keys:
            page_id = self.page_index.record_to_page(key)
            record = shadow[key]
            page = self.committed_pool.get_page(page_id)
            if page is None:
                page = self.page_io.page_in(page_id)
                self.committed_pool.put_page(page_id, page)
            if record.deleted:
                page.delete(key)
            else:
                page.put(key, record)
            self.page_io.page_out(page)
        self.locker.unlock_all(xid)
        return True

    def abort(self, xid: int) -> None:
        """
        Abort a transaction.

        Effects:
            - All shadow pages of this transaction are discarded.
            - No changes are written to the database.
            - Committed state remains unchanged.

        Args:
            xid (int):
                Transaction identifier.
        """
        ...
