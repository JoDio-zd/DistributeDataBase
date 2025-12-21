import time
import pymysql

from src.rm.resource_manager import ResourceManager
from src.rm.impl.page_index.order_string_page_index import OrderedStringPageIndex
from src.rm.impl.page_io.mysql_page_io import MySQLPageIO
from src.rm.base.err_code import ErrCode


# -----------------------------
# DB config
# -----------------------------
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 33061
MYSQL_USER = "root"
MYSQL_PASS = "1234"
MYSQL_DB = "rm_db"

TABLE = "FLIGHTS"
KEY_COL = "flightNum"
KEY_WIDTH = 4
PAGE_SIZE = 2


# -----------------------------
# Helpers
# -----------------------------
def conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASS,
        database=MYSQL_DB,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def build_rm(c):
    page_index = OrderedStringPageIndex(PAGE_SIZE, KEY_WIDTH)
    page_io = MySQLPageIO(
        conn=c,
        table=TABLE,
        key_column=KEY_COL,
        page_index=page_index,
    )
    return ResourceManager(
        page_index=page_index,
        page_io=page_io,
        table=TABLE,
        key_column=KEY_COL,
        key_width=KEY_WIDTH,
    )


def delete_flight(c, key):
    key = key.zfill(KEY_WIDTH)
    with c.cursor() as cur:
        cur.execute(f"DELETE FROM {TABLE} WHERE {KEY_COL}=%s", (key,))
    c.commit()


def seed_flight(rm, c, key, seats=10):
    delete_flight(c, key)

    xid = 999
    r = rm.insert(xid, {
        "flightNum": key,
        "price": 100,
        "numSeats": seats,
        "numAvail": seats,
    })
    assert r.ok
    assert rm.prepare(xid).ok
    rm.commit(xid)


def gen_key(tag):
    t = int(time.time() * 1000) % 10000
    return str((t + abs(hash(tag)) % 1000) % 10000).zfill(4)


# -----------------------------
# Assertions
# -----------------------------
def expect_ok(r, msg):
    if not r.ok:
        print(f"[FAIL] {msg} err={r.err}")
        return False
    return True


def expect_fail(r, expect, msg):
    if r.ok:
        print(f"[FAIL] {msg} should fail")
        return False
    if r.err != expect:
        print(f"[FAIL] {msg} err={r.err}, expect={expect}")
        return False
    return True


# =========================================================
# Level2 Tests – Transaction Lifecycle
# =========================================================

def test_prepare_idempotent():
    print("\n[TEST] prepare idempotent")
    c = conn()
    rm = build_rm(c)

    key = gen_key("prep_idem")
    seed_flight(rm, c, key)

    rm.update(1, key, {"price": 111})

    ok = True
    ok &= expect_ok(rm.prepare(1), "prepare #1")
    ok &= expect_ok(rm.prepare(1), "prepare #2 (idempotent)")

    rm.commit(1)
    c.close()
    return ok


def test_commit_idempotent():
    print("\n[TEST] commit idempotent")
    c = conn()
    rm = build_rm(c)

    key = gen_key("commit_idem")
    print("key = ", key)
    seed_flight(rm, c, key)

    rm.update(1, key, {"price": 222})
    expect_ok(rm.prepare(1), "prepare")

    ok = True
    ok &= expect_ok(rm.commit(1), "commit #1")
    ok &= expect_ok(rm.commit(1), "commit #2 (idempotent)")

    c.close()
    return ok


def test_abort_idempotent():
    print("\n[TEST] abort idempotent")
    c = conn()
    rm = build_rm(c)

    key = gen_key("abort_idem")
    seed_flight(rm, c, key)

    rm.update(1, key, {"price": 333})

    ok = True
    ok &= expect_ok(rm.abort(1), "abort #1")
    ok &= expect_ok(rm.abort(1), "abort #2 (idempotent)")

    c.close()
    return ok


def test_commit_without_prepare():
    print("\n[TEST] commit without prepare rejected")
    c = conn()
    rm = build_rm(c)

    key = gen_key("commit_no_prepare")
    seed_flight(rm, c, key)

    rm.update(1, key, {"price": 444})

    r = rm.commit(1)
    ok = expect_fail(r, ErrCode.INVALID_TX_STATE, "commit before prepare")

    rm.abort(1)
    c.close()
    return ok


def test_prepare_after_abort():
    print("\n[TEST] prepare after abort rejected")
    c = conn()
    rm = build_rm(c)

    key = gen_key("prepare_after_abort")
    seed_flight(rm, c, key)

    rm.update(1, key, {"price": 555})
    rm.abort(1)

    r = rm.prepare(1)
    ok = expect_fail(r, ErrCode.INVALID_TX_STATE, "prepare after abort")

    c.close()
    return ok


def test_update_after_prepare_rejected():
    print("\n[TEST] update after prepare rejected")
    c = conn()
    rm = build_rm(c)

    key = gen_key("update_after_prepare")
    seed_flight(rm, c, key)

    rm.update(1, key, {"price": 666})
    expect_ok(rm.prepare(1), "prepare")

    r = rm.update(1, key, {"price": 777})
    ok = expect_fail(r, ErrCode.INVALID_TX_STATE, "update after prepare")

    rm.abort(1)
    c.close()
    return ok


def test_reuse_key_across_txn():
    print("\n[TEST] reuse key across transactions")
    c = conn()
    rm = build_rm(c)

    key = gen_key("reuse_key")
    seed_flight(rm, c, key)

    rm.update(1, key, {"price": 1000})
    expect_ok(rm.prepare(1), "prepare txn1")
    rm.commit(1)

    rm.update(2, key, {"price": 2000})
    ok = True
    ok &= expect_ok(rm.prepare(2), "prepare txn2")
    ok &= expect_ok(rm.commit(2), "commit txn2")

    c.close()
    return ok


# =========================================================
# Runner
# =========================================================

def run_all():
    tests = [
        test_prepare_idempotent,
        test_commit_idempotent,
        test_abort_idempotent,
        test_commit_without_prepare,
        test_prepare_after_abort,
        test_update_after_prepare_rejected,
        test_reuse_key_across_txn,
    ]

    passed = 0
    for t in tests:
        try:
            if t():
                print("  -> PASS")
                passed += 1
            else:
                print("  -> FAIL")
        except Exception as e:
            print("  -> EXCEPTION:", e)

    print(f"\nRESULT: {passed}/{len(tests)} passed")


if __name__ == "__main__":
    run_all()
