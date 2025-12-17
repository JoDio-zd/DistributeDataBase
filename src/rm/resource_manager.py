from src.rm.impl.mysql_page_io import MySQLPageIO
from src.rm.impl.committed_page_pool import CommittedPagePool
from src.rm.impl.simple_shadow_page_pool import SimpleShadowPagePool
from src.rm.impl.order_string_page_index import OrderedStringPageIndex


class ResourceManager:
    """
    ResourceManager (RM) v1

    A page-based transactional resource manager with copy-on-write semantics.

    Design highlights:
    - Data is accessed and cached in logical pages.
    - All uncommitted modifications are isolated in per-transaction shadow pages.
    - Committed state is never modified before commit.
    - Page-in is performed lazily on cache miss.
    - Page-out is triggered only at commit time.
    - prepare() is provided as a placeholder for future 2PC or validation logic.

    This class acts as a *facade*:
    users of RM do NOT need to know about PageIO, PageIndex, or page pools.
    """

    def __init__(
        self,
        *,
        db_conn,
        table: str,
        key_column: str,
        page_size: int = 2,
        key_width: int = 4,
    ):
        """
        Initialize a ResourceManager instance.

        Args:
            db_conn:
                Database connection handle.
                The RM itself does not manage transactions at the DB level;
                this connection is used only for page-in and page-out operations.

            table (str):
                Name of the database table managed by this RM.
                Each RM instance is responsible for exactly one logical resource
                (e.g., FLIGHTS, HOTELS, CARS).

            key_column (str):
                Name of the primary key column in the table.
                Keys are assumed to be unique and comparable (e.g., VARCHAR).

            page_size (int, optional):
                Number of records per logical page.
                Pages are defined over the ordered key space of the table.
                Default is 10.

            buffer_size (int, optional):
                Maximum number of committed pages cached in memory.
                This controls the size of the committed page pool.
                Eviction policies are not implemented in v1.
        """

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
        self.shadow_pool = SimpleShadowPagePool()
        self.global_last_commit_xid = 0
        self.txn_start_xid = {}

    # =========================================================
    # Internal helper methods
    # =========================================================

    def _ensure_committed_page(self, page_id: int):
        """
        Ensure that a committed page is present in the committed page pool.

        If the page is not cached, it is loaded from the database via page-in
        and inserted into the committed page pool.

        Args:
            page_id (int):
                Logical page identifier.

        Returns:
            Page:
                The committed page instance.
        """
        ...

    def _get_page(self, xid: int, page_id, for_write: bool):
        """
        Core page access logic implementing read and write semantics.

        Read semantics:
            - If a shadow page exists for this transaction, read from it.
            - Otherwise, read from the committed page.

        Write semantics:
            - On the first write to a page within a transaction,
              a shadow copy is created using copy-on-write.
            - Subsequent writes reuse the existing shadow page.

        Args:
            xid (int):
                Transaction identifier.

            page_id:
                Logical page identifier.

            for_write (bool):
                Whether the access is for a write operation.

        Returns:
            Page:
                The page instance visible to this transaction.
        """
        self.txn_start_xid.setdefault(xid, self.global_last_commit_xid)
        if not for_write:
            if self.shadow_pool.has_page(xid, page_id):
                print("Read from shadow page.")
                return self.shadow_pool.get_page(xid, page_id)

            page = self.committed_pool.get_page(page_id)
            if page is not None:
                print("Committed page found in pool.")
                return page

            page = self.page_io.page_in(page_id)
            self.committed_pool.put_page(page_id, page)
            print("Committed page loaded from DB.")
            return page
        else:
            if self.shadow_pool.has_page(xid, page_id):
                print("Shadow page found for txn.")
                return self.shadow_pool.get_page(xid, page_id)

            page = self.committed_pool.get_page(page_id)
            if page is None:
                page = self.page_io.page_in(page_id)
                self.committed_pool.put_page(page_id, page)
                print("Committed page loaded from DB for shadow.")

            self.shadow_pool.put_page(xid, page_id, page)
            print("Shadow page created for txn.")
            return self.shadow_pool.get_page(xid, page_id)

    # =========================================================
    # Data operations (used by WC / business logic)
    # =========================================================

    def read(self, xid: int, key):
        """
        Read a single record by key within a transaction.

        The read observes the transaction's own uncommitted changes
        (if any), otherwise falls back to the committed state.

        Args:
            xid (int):
                Transaction identifier.

            key:
                Primary key value of the record to read.

        Returns:
            dict or None:
                The record if found, otherwise None.
        """
        key = key.zfill(self.key_width)
        page_id = self.page_index.record_to_page(key)
        page = self._get_page(xid, page_id, for_write=False)
        return page.get(key)


    def upsert(self, xid: int, record: dict) -> None:
        """
        Insert or update a record within a transaction.

        This operation never modifies committed state directly.
        A shadow page is created on first write if necessary.

        Args:
            xid (int):
                Transaction identifier.

            record (dict):
                Record data to insert or update.
                Must contain the primary key field.
        """
        key = record[self.key_field].zfill(self.key_width)
        page_id = self.page_index.record_to_page(key)
        page = self._get_page(xid, page_id, for_write=True)
        page.put(key, record)

    def delete(self, xid: int, key) -> None:
        """
        Delete a record by key within a transaction.

        Deletions are applied to shadow pages and become visible
        only after commit.

        Args:
            xid (int):
                Transaction identifier.

            key:
                Primary key value of the record to delete.
        """
        key = key.zfill(self.key_width)
        page_id = self.page_index.record_to_page(key)
        page = self._get_page(xid, page_id, for_write=True)
        page.delete(key)

    # =========================================================
    # Transaction control (used by TM)
    # =========================================================

    def prepare(self, xid: int) -> bool:
        """
        Prepare phase of the transaction (placeholder in v1).

        In v1, this method always returns True, assuming that all
        local operations have succeeded.

        In future versions, this method may perform:
            - Constraint validation
            - Conflict detection
            - RM-local consistency checks

        Args:
            xid (int):
                Transaction identifier.

        Returns:
            bool:
                True if the transaction can be committed, False otherwise.
        """
        return True

    def commit(self, xid: int) -> None:
        """
        Commit a transaction.

        Effects:
            - All shadow pages of this transaction are merged into
              the committed page pool.
            - Modified records are persisted to the database via page-out.
            - All transaction-local state is cleaned up.

        Args:
            xid (int):
                Transaction identifier.
        """
        shadow_pages = self.shadow_pool.get_page_xids(xid)
        if not shadow_pages:
            return True

        start_xid = self.txn_start_xid[xid]
        for page_id, shadow in shadow_pages.items():
            committed = self.committed_pool.get_page(page_id)
            if committed and committed.last_commit_xid > start_xid:
                self.shadow_pool.remove_txn(xid)
                self.txn_start_xid.pop(xid, None)
                return False

        for page_id, shadow in shadow_pages.items():
            shadow.last_commit_xid = xid
            self.committed_pool.put_page(page_id, shadow)
            self.page_io.page_out(shadow)
        
        self.global_last_commit_xid += 1
        self.shadow_pool.remove_txn(xid)
        self.txn_start_xid.pop(xid, None)
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
