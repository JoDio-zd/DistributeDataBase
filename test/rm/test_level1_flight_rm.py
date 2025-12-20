import os
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

    xid = 100
    r = rm.insert(xid, {
        "flightNum": key,
        "price": 100,
        "numSeats": seats,
        "numAvail": seats,
    })
    assert r.ok

    p = rm.prepare(xid)
    assert p.ok

    rm.commit(xid)


def gen_key(tag):
    t = int(time.time() * 1000) % 10000
    return str((t + abs(hash(tag)) % 1000) % 10000).zfill(4)


# -----------------------------
# Assertions (no pytest)
# -----------------------------
def expect_prepare_ok(rm, xid):
    r = rm.prepare(xid)
    if not r.ok:
        print(f"[FAIL] prepare({xid}) unexpected error:", r.err)
        return False
    return True


def expect_prepare_fail(rm, xid, expect):
    r = rm.prepare(xid)
    if r.ok:
        print(f"[FAIL] prepare({xid}) should fail but OK")
        return False
    if r.err != expect:
        print(f"[FAIL] prepare({xid}) err={r.err}, expected={expect}")
        return False
    rm.abort(xid)
    return True


# =========================================================
# Level 1 tests
# =========================================================

def test_rr():
    print("\n[TEST] RR allowed")
    c = conn()
    rm = build_rm(c)

    key = gen_key("rr")
    seed_flight(rm, c, key)

    assert rm.read(1, key).ok
    assert rm.read(2, key).ok

    ok = expect_prepare_ok(rm, 1) and expect_prepare_ok(rm, 2)
    if ok:
        rm.commit(1)
        rm.commit(2)

    c.close()
    return ok


def test_rw():
    print("\n[TEST] RW rejected")
    c = conn()
    rm = build_rm(c)

    key = gen_key("rw")
    print("key =", key)
    seed_flight(rm, c, key)

    assert rm.read(1, key).ok

    rm.update(2, key, {"price": 999})
    expect_prepare_ok(rm, 2)
    rm.commit(2)

    # import pdb; pdb.set_trace()
    ok = expect_prepare_fail(rm, 1, ErrCode.READ_WRITE_CONFLICT)
    c.close()
    return ok


def test_wr():
    print("\n[TEST] WR rejected")
    c = conn()
    rm = build_rm(c)

    key = gen_key("wr")
    seed_flight(rm, c, key)

    assert rm.read(2, key).ok

    rm.update(1, key, {"price": 777})
    expect_prepare_ok(rm, 1)
    rm.commit(1)

    ok = expect_prepare_fail(rm, 2, ErrCode.READ_WRITE_CONFLICT)
    c.close()
    return ok


def test_ww():
    print("\n[TEST] WW rejected")
    c = conn()
    rm = build_rm(c)

    key = gen_key("ww")
    seed_flight(rm, c, key)

    rm.update(1, key, {"price": 200})
    rm.update(2, key, {"price": 300})

    expect_prepare_ok(rm, 1)
    rm.commit(1)

    ok = expect_prepare_fail(rm, 2, ErrCode.VERSION_CONFLICT)
    c.close()
    return ok


def test_insert_insert():
    print("\n[TEST] II rejected")
    c = conn()
    rm = build_rm(c)

    key = gen_key("ii")
    delete_flight(c, key)

    rm.insert(1, {"flightNum": key, "price": 100, "numSeats": 10, "numAvail": 10})
    rm.insert(2, {"flightNum": key, "price": 999, "numSeats": 10, "numAvail": 10})

    expect_prepare_ok(rm, 1)
    rm.commit(1)

    ok = expect_prepare_fail(rm, 2, ErrCode.KEY_EXISTS)
    c.close()
    return ok


def test_update_delete():
    print("\n[TEST] UD rejected")
    c = conn()
    rm = build_rm(c)

    key = gen_key("ud")
    seed_flight(rm, c, key)

    rm.update(1, key, {"price": 555})
    rm.delete(2, key)

    expect_prepare_ok(rm, 1)
    rm.commit(1)

    ok = expect_prepare_fail(rm, 2, ErrCode.VERSION_CONFLICT)
    c.close()
    return ok


# =========================================================
# Runner
# =========================================================

def run_all():
    tests = [
        test_rr,
        test_rw,
        test_wr,
        test_ww,
        test_insert_insert,
        test_update_delete,
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
