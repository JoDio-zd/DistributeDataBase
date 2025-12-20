import pymysql

from src.rm.base.err_code import ErrCode
from src.rm.impl.mysql_page_io import MySQLPageIO
from src.rm.impl.order_string_page_index import OrderedStringPageIndex
from src.rm.resource_manager import ResourceManager

# -----------------------------
# helpers
# -----------------------------


def new_conn():
    return pymysql.connect(
        host="127.0.0.1",
        port=33061,
        user="root",
        password="1234",
        database="rm_db",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def new_rm(
    conn, *, table: str, key_column: str, page_size: int = 2, key_width: int = 4
):
    page_index = OrderedStringPageIndex(page_size, key_width)
    page_io = MySQLPageIO(
        conn=conn,
        table=table,
        key_column=key_column,
        page_index=page_index,
    )
    return ResourceManager(
        page_index=page_index,
        page_io=page_io,
        table=table,
        key_column=key_column,
        key_width=key_width,
    )


def preload_page_for_key(rm: ResourceManager, xid: int, key: str):
    """
    IMPORTANT: Your RM's prepare() requires committed_pool already has the page loaded.
    The simplest way is to call rm.read() once for that key (even if not found).
    """
    rm.read(xid, key)


def seed_if_absent(rm: ResourceManager, xid: int, record: dict, key_field: str):
    """
    Insert seed record if absent. If exists, do nothing.
    We intentionally do NOT rely on exceptions; only RMResult.
    """
    key = record[key_field]
    # preload the page to satisfy prepare invariant (for the seed txn as well)
    preload_page_for_key(rm, xid, key)

    # If already exists, skip
    r = rm.read(xid, key)
    if r.ok:
        rm.abort(xid)  # cleanup txn state (optional but keeps rm.txn_start_xid clean)
        return

    ins = rm.insert(xid, record)
    assert ins.ok, f"seed insert failed unexpectedly: {ins.err}"
    p = rm.prepare(xid)
    assert p.ok, f"seed prepare failed unexpectedly: {p.err}"
    rm.commit(xid)


def read_committed_like(rm: ResourceManager, key: str):
    """
    A helper to read final committed state using a fresh xid.
    (RM allows reads without explicit start/commit; but still creates txn_start_xid entry.)
    """
    xid = 9999
    r = rm.read(xid, key)
    assert r.ok, f"final read failed: {r.err}"
    return r.value


# =========================================================
# tests
# =========================================================


def test_ww_conflict_insert_insert_simulated():
    conn = new_conn()
    rm = new_rm(conn, table="FLIGHTS", key_column="flightNum", page_size=2, key_width=4)

    key = "3456"

    # 0) preload page for BOTH txns (required by your prepare invariant)
    preload_page_for_key(rm, 1, key)
    preload_page_for_key(rm, 2, key)

    # 1) T1/T2 both insert same key
    r1 = rm.insert(
        1,
        {
            "flightNum": key,
            "price": 300,
            "numSeats": 150,
            "numAvail": 120,
        },
    )
    assert r1.ok, f"T1 insert should succeed into shadow: {r1.err}"

    r2 = rm.insert(
        2,
        {
            "flightNum": key,
            "price": 999,
            "numSeats": 150,
            "numAvail": 100,
        },
    )
    assert r2.ok, f"T2 insert should succeed into shadow: {r2.err}"

    # 2) commit T1
    p1 = rm.prepare(1)
    assert p1.ok, f"T1 prepare should succeed: {p1.err}"
    rm.commit(1)

    # 3) prepare T2 must fail (KEY_EXISTS)
    p2 = rm.prepare(2)
    assert not p2.ok, "T2 prepare should fail due to T1 committed insert"
    assert p2.err == ErrCode.KEY_EXISTS, f"expected KEY_EXISTS, got {p2.err}"
    rm.abort(2)

    # 4) final state should be T1's price
    final = read_committed_like(rm, key)
    assert final["price"] == 300, f"expected committed price=300, got {final['price']}"

    conn.close()


def test_ww_conflict_update_update_simulated():
    conn = new_conn()
    rm = new_rm(conn, table="FLIGHTS", key_column="flightNum", page_size=2, key_width=4)

    key = "7777"

    # 0) seed a committed record if absent
    seed_if_absent(
        rm,
        xid=0,
        record={
            "flightNum": key,
            "price": 100,
            "numSeats": 150,
            "numAvail": 150,
        },
        key_field="flightNum",
    )

    # 1) concurrent reads (establish start_version in txn_start_xid)
    preload_page_for_key(rm, 1, key)
    preload_page_for_key(rm, 2, key)
    r1 = rm.read(1, key)
    r2 = rm.read(2, key)
    assert r1.ok and r2.ok, "both txns should read the committed record"

    # 2) both update
    u1 = rm.update(1, key, {"price": 200})
    assert u1.ok, f"T1 update should succeed into shadow: {u1.err}"
    u2 = rm.update(2, key, {"price": 999})
    assert u2.ok, f"T2 update should succeed into shadow: {u2.err}"

    # 3) commit T1
    p1 = rm.prepare(1)
    assert p1.ok, f"T1 prepare should succeed: {p1.err}"
    rm.commit(1)

    # 4) T2 prepare must fail with VERSION_CONFLICT
    p2 = rm.prepare(2)
    assert not p2.ok, "T2 prepare should fail due to version conflict"
    assert p2.err == ErrCode.VERSION_CONFLICT, (
        f"expected VERSION_CONFLICT, got {p2.err}"
    )
    rm.abort(2)

    # 5) final should be T1
    final = read_committed_like(rm, key)
    assert final["price"] == 200, f"expected committed price=200, got {final['price']}"

    conn.close()


def test_ww_conflict_update_delete_simulated():
    conn = new_conn()
    rm = new_rm(conn, table="FLIGHTS", key_column="flightNum", page_size=2, key_width=4)

    key = "8888"

    # 0) seed record if absent
    seed_if_absent(
        rm,
        xid=0,
        record={
            "flightNum": key,
            "price": 100,
            "numSeats": 150,
            "numAvail": 150,
        },
        key_field="flightNum",
    )

    # 1) concurrent reads
    preload_page_for_key(rm, 1, key)
    preload_page_for_key(rm, 2, key)
    assert rm.read(1, key).ok
    assert rm.read(2, key).ok

    # 2) T1 update, T2 delete
    assert rm.update(1, key, {"price": 200}).ok
    assert rm.delete(2, key).ok

    # 3) commit T1
    p1 = rm.prepare(1)
    assert p1.ok, f"T1 prepare should succeed: {p1.err}"
    rm.commit(1)

    # 4) T2 prepare must fail due to VERSION_CONFLICT (most consistent with your prepare logic)
    p2 = rm.prepare(2)
    assert not p2.ok, "T2 prepare should fail due to version conflict"
    assert p2.err == ErrCode.VERSION_CONFLICT, (
        f"expected VERSION_CONFLICT, got {p2.err}"
    )
    rm.abort(2)

    # 5) final should exist and price=200
    final = read_committed_like(rm, key)
    assert final["price"] == 200
    assert not final.deleted

    conn.close()


if __name__ == "__main__":
    test_ww_conflict_insert_insert_simulated()
    test_ww_conflict_update_update_simulated()
    test_ww_conflict_update_delete_simulated()
    print("all tests passed")
