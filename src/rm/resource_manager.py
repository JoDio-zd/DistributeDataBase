from src.rm.impl.page_io.mysql_page_io import MySQLPageIO
from src.rm.impl.committed_page_pool import CommittedPagePool
from src.rm.impl.simple_shadow_record_pool import SimpleShadowRecordPool
from src.rm.impl.page_index.order_string_page_index import OrderedStringPageIndex
from src.rm.base.page import Record
from src.rm.impl.lock_manager import RowLockManager
from src.rm.base.err_code import RMResult, ErrCode
from src.rm.base.page_io import PageIO
from src.rm.base.page_index import PageIndex
import os
import logging
from typing import Any
import json
import tempfile

logger = logging.getLogger("rm")


class ResourceManager:

    def __init__(
        self,
        *,
        page_index: PageIndex,
        page_io: PageIO,
        table: str,
        key_column: str,
        key_width: int = 4,
    ):
        # Publicly invisible configuration
        self.table = table
        self.key_field = key_column
        self.key_width = key_width

        self.page_index = page_index
        self.page_io = page_io

        self.committed_pool = CommittedPagePool()
        self.shadow_pool = SimpleShadowRecordPool()
        self.global_last_commit_xid = 0
        self.txn_start_xid: dict[int, dict[str, int]] = {}
        self.locker = RowLockManager()
        self.read_set: dict[int, dict[str, int]] = {}
        self.write_set: dict[int, dict[str, int]] = {}
        self.prepared_txns: set[int] = set()
        self.committed_txns: set[int] = set()
        self.aborted_txns: set[int] = set()
        self.state_dir = "rm_txn_state/"
        self.state_path = os.path.join(self.state_dir, f"{table}_rm_state.json")
        self.recover()

        logger.info(
            "ResourceManager initialized: table=%s, key=%s, index=%s, io=%s",
            table,
            key_column,
            type(page_index).__name__,
            type(page_io).__name__,
        )

    # =========================================================
    # Internal helper methods
    # =========================================================

    def _get_record(self, xid: int, key: str, for_write: bool):
        page_id = self.page_index.record_to_page(key)
        logger.debug(
            "RM.get_record: xid=%s key=%s page=%s for_write=%s",
            xid, key, page_id, for_write
        )
        shadow = self.shadow_pool.get_record(xid, key)
        record = None
        if shadow is not None:
            logger.debug("RM.get_record: hit shadow xid=%s key=%s", xid, key)
            record = shadow
        else:
            page = self.committed_pool.get_page(page_id)
            if page is None:
                logger.debug("RM.get_record: page_in page=%s for xid=%s", page_id, xid)
                page = self.page_io.page_in(page_id)
                self.committed_pool.put_page(page_id, page)
            record = page.get(key)
        
        if for_write:
            if shadow is None and record is not None:
                logger.debug(
                    "RM.get_record: create shadow record xid=%s key=%s version=%s",
                    xid, key, record.version
                )
                self.shadow_pool.put_record(xid, key, record)
                record = self.shadow_pool.get_record(xid, key)
        return record
    
    def _get_start_version(self, xid: int, key: str):
        if xid in self.txn_start_xid and key in self.txn_start_xid[xid]:
            logger.debug(
                "RM.get_start_version: xid=%s key=%s start_version=%s",
                xid, key, self.txn_start_xid[xid][key]
            )
            return self.txn_start_xid[xid][key]
        logger.debug(
            "RM.get_start_version: xid=%s key=%s start_version=None", xid, key
        )
        return None
    
    def _ensure_state_dir(self):
        os.makedirs(self.state_dir, exist_ok=True)

    def _load_state_file(self) -> dict[str, Any]:
        """
        State file schema (recommended minimal):
        {
          "prepared": {
            "<xid>": {
              "records": {
                "<key>": {"data": {...}, "deleted": false, "version": 123},
                ...
              }
            },
            ...
          }
        }
        """
        self._ensure_state_dir()
        if not os.path.exists(self.state_path):
            return {"prepared": {}}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if not isinstance(obj, dict):
                return {"prepared": {}}
            obj.setdefault("prepared", {})
            if not isinstance(obj["prepared"], dict):
                obj["prepared"] = {}
            return obj
        except Exception as e:
            logger.exception("RM.state load failed, treat as empty. path=%s err=%s", self.state_path, e)
            return {"prepared": {}}
    
    def _atomic_write_json(self, obj: dict[str, Any], path: str):
        """
        Atomic write: write temp -> fsync -> replace.
        """
        self._ensure_state_dir()
        d = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_rm_state_", dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _persist_prepared_shadow(self, xid: int):
        """
        Persist the prepared shadow records of xid.
        Call this ONLY when prepare is successful and BEFORE returning OK to TM
        if you want "prepared implies commit is doable after crash".
        """
        shadow = self.shadow_pool.get_records(xid) or {}
        state = self._load_state_file()

        xid_s = str(xid)
        recs: dict[str, Any] = {}
        for k, r in shadow.items():
            key = k.zfill(self.key_width)
            # r behaves like Record: dict-like + attrs deleted/version
            # we persist only what's needed to re-create shadow records.
            recs[key] = {
                "data": dict(r),  # copy underlying dict fields
                "deleted": bool(getattr(r, "deleted", False)),
                "version": int(getattr(r, "version", xid)),
            }

        state["prepared"][xid_s] = {"records": recs}
        self._atomic_write_json(state, self.state_path)

    def _clear_persisted_txn(self, xid: int):
        """
        Remove xid from state file when txn is fully resolved (commit/abort).
        """
        state = self._load_state_file()
        xid_s = str(xid)
        if xid_s in state.get("prepared", {}):
            state["prepared"].pop(xid_s, None)
            self._atomic_write_json(state, self.state_path)

    # =========================================================
    # function
    # =========================================================
    def read(self, xid: int, key):
        if xid in self.prepared_txns or xid in self.committed_txns or xid in self.aborted_txns:
            logger.warning(
                "RM.update invalid state: xid=%s already prepared/committed/aborted", xid
            )
            return RMResult(ok=False, err=ErrCode.INVALID_TX_STATE)
        key = key.zfill(self.key_width)
        record = self._get_record(xid, key, for_write=False)
        if record is None or record.deleted:
            return RMResult(ok=False, err=ErrCode.KEY_NOT_FOUND)
        if xid not in self.txn_start_xid:
            self.txn_start_xid[xid] = {}
        if key not in self.txn_start_xid[xid]:
            self.txn_start_xid[xid][key] = record.version
        if xid not in self.write_set:
            self.read_set[xid] = {}
            self.read_set[xid][key] = record.version
        return RMResult(ok=True, value=record)

    def insert(self, xid: int, record: dict) -> None:
        if xid in self.prepared_txns or xid in self.committed_txns or xid in self.aborted_txns:
            logger.warning(
                "RM.update invalid state: xid=%s already prepared/committed/aborted", xid
            )
            return RMResult(ok=False, err=ErrCode.INVALID_TX_STATE)
        # For Insert operation, we assume the record contains the key field.
        key = record[self.key_field].zfill(self.key_width)
        if xid in self.read_set and key in self.read_set[xid]:
            self.read_set[xid].pop(key)
        record[self.key_field] = key
        logger.info("RM.insert: xid=%s key=%s", xid, key)
        record_existed = self._get_record(xid, key, for_write=False)
        if record_existed is not None and not record_existed.deleted:
            logger.warning(
                "RM.insert conflict: xid=%s key=%s already exists",
                xid, key
            )
            return RMResult(ok=False, err=ErrCode.KEY_EXISTS)
        record = Record(record, version=xid)
        self.shadow_pool.put_record(xid, key, record)
        if xid not in self.write_set:
            self.write_set[xid] = {}
            self.write_set[xid][key] = record.version
        logger.info(
            "RM.insert success: xid=%s key=%s version=%s",
            xid, key, xid
        )
        return RMResult(ok=True, value=record)
    
    def delete(self, xid: int, key) -> None:
        if xid in self.prepared_txns or xid in self.committed_txns or xid in self.aborted_txns:
            logger.warning(
                "RM.update invalid state: xid=%s already prepared/committed/aborted", xid
            )
            return RMResult(ok=False, err=ErrCode.INVALID_TX_STATE)
        if xid in self.read_set and key in self.read_set[xid]:
            self.read_set[xid].pop(key)
        key = key.zfill(self.key_width)
        record = self._get_record(xid, key, for_write=True)
        logger.info("RM.delete: xid=%s key=%s, version=%s", xid, key, record.version if record else None)
        if record is None or record.deleted:
            return RMResult(ok=False, err=ErrCode.KEY_NOT_FOUND)
        self.txn_start_xid.setdefault(xid, {})[key] = record.version
        record.deleted = True
        record.version = xid
        if xid not in self.write_set:
            self.write_set[xid] = {}
            self.write_set[xid][key] = record.version
        return RMResult(ok=True, value=record)

    def update(self, xid: int, key: str, updates: dict) -> None:
        if xid in self.prepared_txns or xid in self.committed_txns or xid in self.aborted_txns:
            logger.warning(
                "RM.update invalid state: xid=%s already prepared/committed/aborted", xid
            )
            return RMResult(ok=False, err=ErrCode.INVALID_TX_STATE)
        if xid in self.read_set and key in self.read_set[xid]:
            self.read_set[xid].pop(key)
        key = key.zfill(self.key_width)
        logger.info("RM.update: xid=%s key=%s updates=%s", xid, key, list(updates.keys()))
        record = self._get_record(xid, key, for_write=True)
        if record is None or record.deleted:
            logger.warning(
                "RM.update not found: xid=%s key=%s",
                xid, key
            )
            return RMResult(ok=False, err=ErrCode.KEY_NOT_FOUND)
        if xid not in self.txn_start_xid:
            self.txn_start_xid[xid] = {}
            self.txn_start_xid[xid][key] = record.version
        else:
            if key not in self.txn_start_xid[xid]:
                self.txn_start_xid[xid][key] = record.version
        for field, value in updates.items():
            record[field] = value
        record.version = xid
        if xid not in self.write_set:
            self.write_set.setdefault(xid, {})
            self.write_set[xid].setdefault(key, record.version)
        logger.info(
            "RM.update success: xid=%s key=%s start_version=%s",
            xid, key, self._get_start_version(xid, key)
        )
        return RMResult(ok=True, value=record)
        

    # =========================================================
    # Transaction control (used by TM)
    # =========================================================

    def prepare(self, xid: int) -> bool:
        if xid in self.aborted_txns:
            logger.warning(
                "RM.prepare invalid state: xid=%s already aborted", xid
            )
            return RMResult(ok=False, err=ErrCode.INVALID_TX_STATE)
        shadow = self.shadow_pool.get_records(xid)
        logger.info("RM.prepare start: xid=%s", xid)
        keys = sorted(k.zfill(self.key_width) for k in shadow.keys())
        for key in keys:
            if not self.locker.try_lock(key, xid):
                self.locker.unlock_all(xid)
                logger.warning(
                    "RM.prepare lock conflict: xid=%s key=%s",
                    xid, key
                )
                return RMResult(ok=False, err=ErrCode.LOCK_CONFLICT)
            
        for key, record in shadow.items():
            page_id = self.page_index.record_to_page(key)
            page = self.committed_pool.get_page(page_id)
            if page is None:
                logger.error(
                    "RM.prepare invariant violation: xid=%s page=%s not loaded",
                    xid, page_id
                )
                return RMResult(ok=False, err=ErrCode.INTERNAL_INVARIANT)
            committed_record = page.get(key)
            start_version = self._get_start_version(xid, key)

            # -------- INSERT --------
            if start_version is None:
                if committed_record is not None and not committed_record.deleted:
                    self.locker.unlock_all(xid)
                    logger.warning(
                        "RM.prepare semantic conflict: xid=%s key=%s err=%s",
                        xid, key, ErrCode.KEY_EXISTS.name
                    )
                    return RMResult(ok=False, err=ErrCode.KEY_EXISTS)
                continue

            # -------- UPDATE / DELETE --------
            if committed_record is None or committed_record.deleted:
                if not record.deleted:
                    self.locker.unlock_all(xid)
                    logger.warning(
                        "RM.prepare semantic conflict: xid=%s key=%s err=%s",
                        xid, key, ErrCode.KEY_EXISTS.name
                    )
                    return RMResult(ok=False, err=ErrCode.KEY_NOT_FOUND)
                continue

            # version 校验
            if committed_record.version != start_version:
                self.locker.unlock_all(xid)
                logger.warning(
                    "RM.prepare version conflict: xid=%s key=%s committed=%s start=%s",
                    xid, key, committed_record.version, start_version
                )
                return RMResult(ok=False, err=ErrCode.VERSION_CONFLICT)
        for xid_ in self.read_set.keys():
            if xid_ == xid:
                for key_ in self.read_set[xid_]:
                    if self.read_set[xid_][key_] != self._get_record(xid_, key_, False).version:
                        self.locker.unlock_all(xid)
                        logger.warning(
                            "RM.prepare read-write conflict: xid=%s key=%s",
                            xid, key_
                        )
                        return RMResult(ok=False, err=ErrCode.READ_WRITE_CONFLICT)
        try:
            self._persist_prepared_shadow(xid)
        except Exception:
            self.locker.unlock_all(xid)
            self.shadow_pool.remove_txn(xid)
            self.txn_start_xid.pop(xid, None)
            self._clear_persisted_txn(xid)
            return RMResult(ok=False, err=ErrCode.INTERNAL_INVARIANT)
        
        logger.info(
            "RM.prepare success: xid=%s keys=%s",
            xid, list(shadow.keys())
        )
        self.prepared_txns.add(xid)
        return RMResult(ok=True, value=None)

    def commit(self, xid: int) -> None:
        if xid in self.committed_txns:
            logger.info("RM.commit idem: xid=%s already committed", xid)
            return RMResult(ok=True, value=None)
        if xid not in self.prepared_txns:
            logger.warning(
                "RM.commit invalid state: xid=%s not prepared", xid
            )
            return RMResult(ok=False, err=ErrCode.INVALID_TX_STATE)
        shadow = self.shadow_pool.get_records(xid)
        logger.info(
            "RM.commit start: xid=%s records=%d",
            xid, len(shadow)
        )
        keys = sorted(k.zfill(self.key_width) for k in shadow.keys())
        pages_written = {}
        for key in keys:
            page_id = self.page_index.record_to_page(key)
            record = shadow[key]
            page = self.committed_pool.get_page(page_id)
            logger.debug(
                "RM.commit apply: xid=%s key=%s deleted=%s, version=%s",
                xid, key, record.deleted, record.version
            )
            if page is None:
                page = self.page_io.page_in(page_id)
            if record.deleted:
                page.delete(key)
            else:
                page.put(key, record)
            self.committed_pool.put_page(page_id, page)
            pages_written[page_id] = page
        for page_id in pages_written.keys():
            self.page_io.page_out(pages_written[page_id])
        self.locker.unlock_all(xid)
        self.shadow_pool.remove_txn(xid)
        self.txn_start_xid.pop(xid, None)
        logger.info("RM.commit done: xid=%s", xid)
        self.prepared_txns.discard(xid)
        self.committed_txns.add(xid)
        self._clear_persisted_txn(xid)
        return RMResult(ok=True, value=None)

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
        if xid in self.aborted_txns:
            return RMResult(ok=True)
        self.shadow_pool.remove_txn(xid)
        self.txn_start_xid.pop(xid, None)
        self.locker.unlock_all(xid)
        logger.info("RM.abort: xid=%s", xid)
        self.prepared_txns.discard(xid)
        self.aborted_txns.add(xid)
        self._clear_persisted_txn(xid)
        return RMResult(ok=True, value=None)
    
    def recover(self):
        """
        Crash recovery for RM.

        Goal:
          - restore PREPARED-but-undecided transactions:
              * reload their shadow records into shadow_pool
              * mark them as prepared_txns
              * re-acquire write locks on involved keys
          - DO NOT re-run semantic/version validation (do NOT "prepare again")
          - must be invoked BEFORE the RM starts serving new requests
        """
        state = self._load_state_file()
        prepared: dict[str, Any] = state.get("prepared", {})
        if not prepared:
            logger.info("RM.recover: no prepared txns. table=%s", getattr(self, "table", ""))
            return

        logger.warning("RM.recover: start, prepared_txns=%d path=%s", len(prepared), self.state_path)

        # Recover each prepared xid
        for xid_s, info in prepared.items():
            try:
                xid = int(xid_s)
            except ValueError:
                logger.warning("RM.recover: skip invalid xid key=%s", xid_s)
                continue

            # Rebuild shadow records
            records = (info or {}).get("records", {}) or {}
            if not isinstance(records, dict):
                logger.warning("RM.recover: xid=%s records malformed, skip", xid)
                continue

            # Load shadow records into shadow_pool
            keys = sorted(k.zfill(self.key_width) for k in records.keys())
            for key in keys:
                payload = records.get(key, {})
                data = payload.get("data", {}) or {}
                deleted = bool(payload.get("deleted", False))
                version = int(payload.get("version", xid))

                rec = Record(dict(data), version=version)
                rec.deleted = deleted
                # 注意：insert/update/delete 都是通过 shadow_pool 来提供 commit 输入
                self.shadow_pool.put_record(xid, key, rec)

            # Mark prepared (in-memory)
            self.prepared_txns.add(xid)

            # Re-acquire locks for this prepared transaction.
            # Important: do NOT validate versions/semantics again.
            for key in keys:
                if not self.locker.try_lock(key, xid):
                    # 这个情况通常只会发生在“恢复时已经开始对外服务”的错误启动顺序
                    # 或者锁管理器本身不是“空状态启动”。
                    logger.critical(
                        "RM.recover: lock acquisition failed for prepared txn. xid=%s key=%s. "
                        "Refuse to serve to avoid violating 2PC semantics.",
                        xid, key
                    )
                    raise RuntimeError(f"RM recovery lock failed: xid={xid} key={key}")

            logger.warning("RM.recover: restored prepared txn xid=%s keys=%d", xid, len(keys))

        logger.warning("RM.recover: done. prepared_in_mem=%d", len(self.prepared_txns))