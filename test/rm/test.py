import itertools
import time

import pymysql

from src.rm.base.err_code import ErrCode
from src.rm.impl.mysql_page_io import MySQLPageIO
from src.rm.impl.order_string_page_index import OrderedStringPageIndex
from src.rm.resource_manager import ResourceManager

RUN_ID = time.strftime("%Y%m%d%H%M%S")
_xid_gen = itertools.count(1)
_key_gen = itertools.count(1)


def next_xid() -> int:
    # 生成唯一 xid，模拟递增事务
    return next(_xid_gen)


def new_key(tag: str) -> str:
    # 保持数字/字母，便于落在既有 page 范围内
    return f"{RUN_ID}{next(_key_gen):03d}{tag}"


def make_rm():
    conn = pymysql.connect(
        host="127.0.0.1",
        port=33061,
        user="root",
        password="1234",
        database="rm_db",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    page_index = OrderedStringPageIndex(page_size=2, key_width=4)
    page_io = MySQLPageIO(
        conn=conn,
        table="FLIGHTS",
        key_column="flightNum",
        page_index=page_index,
    )
    rm = ResourceManager(
        page_index=page_index,
        page_io=page_io,
        table="FLIGHTS",
        key_column="flightNum",
        key_width=4,
    )
    return rm, conn


def assert_ok(res, msg: str = ""):
    assert res.ok, f"{msg} err={res.err}"
    return res.value


def assert_err(res, err: ErrCode):
    assert not res.ok and res.err == err, f"expected {err}, got {res.err}"


def seed_committed_record(rm, key: str, price: int = 100, seats: int = 3):
    xid = next_xid()
    assert_ok(
        rm.insert(
            xid,
            {
                "flightNum": key,
                "price": price,
                "numSeats": seats,
                "numAvail": seats,
            },
        )
    )
    assert_ok(rm.prepare(xid))
    assert_ok(rm.commit(xid))


# WW 插入 vs 插入：只有第一个能 commit
def test_ww_conflict_insert_insert_simulated():
    rm, conn = make_rm()
    try:
        key = new_key("I")
        # 预加载 page，避免 prepare 缺页断言
        rm.read(next_xid(), key)

        assert_ok(
            rm.insert(
                1,
                {
                    "flightNum": key,
                    "price": 300,
                    "numSeats": 150,
                    "numAvail": 120,
                },
            )
        )
        assert_ok(
            rm.insert(
                2,
                {
                    "flightNum": key,
                    "price": 999,
                    "numSeats": 150,
                    "numAvail": 100,
                },
            )
        )

        res1 = rm.prepare(1)
        assert_ok(res1)
        assert_ok(rm.commit(1))

        res2 = rm.prepare(2)
        assert_err(res2, ErrCode.KEY_EXISTS)
        assert_ok(rm.abort(2))

        final = rm.read(999, key)
        assert_ok(final)
        assert final.value["price"] == 300
    finally:
        conn.close()


# WW 更新 vs 更新：第二个 prepare 触发版本冲突
def test_ww_conflict_update_update_simulated():
    rm, conn = make_rm()
    try:
        key = new_key("U")
        seed_committed_record(rm, key, price=100, seats=10)

        assert_ok(rm.read(1, key))
        assert_ok(rm.read(2, key))

        assert_ok(rm.update(1, key, {"price": 200}))
        assert_ok(rm.update(2, key, {"price": 999}))

        assert_ok(rm.prepare(1))
        assert_ok(rm.commit(1))

        res2 = rm.prepare(2)
        assert_err(res2, ErrCode.VERSION_CONFLICT)
        assert_ok(rm.abort(2))

        final = rm.read(999, key)
        assert_ok(final)
        assert final.value["price"] == 200
    finally:
        conn.close()


# WW 更新 vs 删除：删除方 prepare 失败
def test_ww_conflict_update_delete_simulated():
    rm, conn = make_rm()
    try:
        key = new_key("D")
        seed_committed_record(rm, key, price=100, seats=10)

        assert_ok(rm.read(1, key))
        assert_ok(rm.read(2, key))

        assert_ok(rm.update(1, key, {"price": 200}))
        assert_ok(rm.delete(2, key))

        assert_ok(rm.prepare(1))
        assert_ok(rm.commit(1))

        res2 = rm.prepare(2)
        assert_err(res2, ErrCode.VERSION_CONFLICT)
        assert_ok(rm.abort(2))

        final = rm.read(999, key)
        assert_ok(final)
        assert final.value["price"] == 200
    finally:
        conn.close()


# 提交后读到新记录
def test_commit_visibility():
    rm, conn = make_rm()
    try:
        key = new_key("CV")
        xid1 = next_xid()
        assert_ok(
            rm.insert(
                xid1,
                {
                    "flightNum": key,
                    "price": 123,
                    "numSeats": 5,
                    "numAvail": 5,
                },
            )
        )
        assert_ok(rm.prepare(xid1))
        assert_ok(rm.commit(xid1))

        res = rm.read(next_xid(), key)
        assert_ok(res)
        assert res.value["numAvail"] == 5
    finally:
        conn.close()


# Abort 丢弃已准备但未提交的写
def test_abort_rolls_back():
    rm, conn = make_rm()
    try:
        key = new_key("AB")
        xid1 = next_xid()
        assert_ok(
            rm.insert(
                xid1,
                {
                    "flightNum": key,
                    "price": 111,
                    "numSeats": 3,
                    "numAvail": 3,
                },
            )
        )
        assert_ok(rm.prepare(xid1))
        assert_ok(rm.abort(xid1))

        res = rm.read(next_xid(), key)
        assert_err(res, ErrCode.KEY_NOT_FOUND)
    finally:
        conn.close()


# prepare 后未提交的写不影响其他读
def test_pred_old_read_sees_committed():
    rm, conn = make_rm()
    try:
        key = new_key("PO")
        seed_committed_record(rm, key, price=50, seats=2)

        xid1 = next_xid()
        assert_ok(rm.update(xid1, key, {"price": 75}))
        assert_ok(rm.prepare(xid1))  # hold lock, not committed

        res = rm.read(next_xid(), key)
        assert_ok(res)
        assert res.value["price"] == 50

        assert_ok(rm.abort(xid1))
    finally:
        conn.close()


# prepare 锁冲突后 abort 释放锁，再写可成功
def test_lock_conflict_then_release():
    rm, conn = make_rm()
    try:
        key = new_key("LC")
        assert_ok(
            rm.insert(
                1,
                {
                    "flightNum": key,
                    "price": 10,
                    "numSeats": 1,
                    "numAvail": 1,
                },
            )
        )
        assert_ok(rm.prepare(1))

        assert_ok(
            rm.insert(
                2,
                {
                    "flightNum": key,
                    "price": 20,
                    "numSeats": 1,
                    "numAvail": 1,
                },
            )
        )
        res2 = rm.prepare(2)
        assert_err(res2, ErrCode.LOCK_CONFLICT)
        assert_ok(rm.abort(2))

        assert_ok(rm.abort(1))

        assert_ok(
            rm.insert(
                3,
                {
                    "flightNum": key,
                    "price": 30,
                    "numSeats": 1,
                    "numAvail": 1,
                },
            )
        )
        assert_ok(rm.prepare(3))
        assert_ok(rm.commit(3))
    finally:
        conn.close()


# 版本冲突被检测到，锁释放后后续事务可继续
def test_version_conflict_and_unlock():
    rm, conn = make_rm()
    try:
        key = new_key("VC")
        seed_committed_record(rm, key, price=10, seats=1)

        xid1 = next_xid()
        xid2 = next_xid()

        res = rm.read(xid1, key)
        assert_ok(res)

        assert_ok(rm.update(xid2, key, {"price": 20}))
        assert_ok(rm.prepare(xid2))
        assert_ok(rm.commit(xid2))

        assert_ok(rm.update(xid1, key, {"price": 30}))
        res_conflict = rm.prepare(xid1)
        assert res_conflict.err in (ErrCode.VERSION_CONFLICT, ErrCode.KEY_NOT_FOUND)
        assert_ok(rm.abort(xid1))

        xid3 = next_xid()
        assert_ok(rm.update(xid3, key, {"price": 40}))
        assert_ok(rm.prepare(xid3))
        assert_ok(rm.commit(xid3))
    finally:
        conn.close()


# commit 幂等，不应破坏状态
def test_commit_idempotent():
    rm, conn = make_rm()
    try:
        key = new_key("CI")
        xid = next_xid()
        assert_ok(
            rm.insert(
                xid,
                {
                    "flightNum": key,
                    "price": 1,
                    "numSeats": 1,
                    "numAvail": 1,
                },
            )
        )
        assert_ok(rm.prepare(xid))
        assert_ok(rm.commit(xid))
        assert_ok(rm.commit(xid))

        res = rm.read(next_xid(), key)
        assert_ok(res)
        assert res.value["price"] == 1
    finally:
        conn.close()


# 先删后插，最终读到新值
def test_delete_then_insert():
    rm, conn = make_rm()
    try:
        key = new_key("DI")
        seed_committed_record(rm, key, price=60, seats=4)

        xid1 = next_xid()
        assert_ok(rm.delete(xid1, key))
        assert_ok(rm.prepare(xid1))
        assert_ok(rm.commit(xid1))

        xid2 = next_xid()
        assert_ok(
            rm.insert(
                xid2,
                {
                    "flightNum": key,
                    "price": 80,
                    "numSeats": 4,
                    "numAvail": 4,
                },
            )
        )
        assert_ok(rm.prepare(xid2))
        assert_ok(rm.commit(xid2))

        res = rm.read(next_xid(), key)
        assert_ok(res)
        assert res.value["price"] == 80
        assert res.value["numAvail"] == 4
    finally:
        conn.close()


def run_all():
    tests = [
        test_ww_conflict_insert_insert_simulated,
        test_ww_conflict_update_update_simulated,
        test_ww_conflict_update_delete_simulated,
        test_commit_visibility,
        test_abort_rolls_back,
        test_pred_old_read_sees_committed,
        test_lock_conflict_then_release,
        test_version_conflict_and_unlock,
        test_commit_idempotent,
        test_delete_then_insert,
    ]
    for t in tests:
        t()


if __name__ == "__main__":
    run_all()
