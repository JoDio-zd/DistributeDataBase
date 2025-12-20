import itertools
import random
import threading
import time
import traceback

import requests

from src.wc.workflow_controller import WC

THREADS = 4
ROUNDS = 20
SLEEP_MAX = 0.01
REQUEST_TIMEOUT = 8
RUN_ID = time.strftime("%H%M%S")
PRICE = 500
SEATS = 2

_name_counter = itertools.count(1)


def _wrap_timeout(fn):
    def inner(*args, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        return fn(*args, **kwargs)

    return inner


def _patch_requests_timeout():
    requests.request = _wrap_timeout(requests.request)
    requests.get = _wrap_timeout(requests.get)
    requests.post = _wrap_timeout(requests.post)
    requests.put = _wrap_timeout(requests.put)
    requests.delete = _wrap_timeout(requests.delete)


_patch_requests_timeout()


def uid(tag: str) -> str:
    return f"{RUN_ID}{next(_name_counter):03d}{tag}"


def tiny_sleep():
    time.sleep(random.uniform(0, SLEEP_MAX))


def run_txn(wc, fn, results, start_barrier):
    xid = None
    try:
        start_barrier.wait()
        xid = wc.start()
        fn(wc, xid)
        wc.commit(xid)
        results.append(("commit", xid))
    except Exception:
        if xid is not None:
            wc.abort(xid)
        results.append(("abort", xid))


def query_reservation(wc: WC, cust: str, resv_type: str, resv_key: str):
    xid = wc.start()
    try:
        resp = requests.get(
            f"{wc.reservation_rm}/records",
            params={
                "custName": cust,
                "resvType": resv_type,
                "resvKey": resv_key,
                "xid": xid,
            },
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("record")
    finally:
        try:
            wc.commit(xid)
        except Exception:
            try:
                wc.abort(xid)
            except Exception:
                pass


# 正常流程：预订扣减库存且写入 reservation
def case_happy_path_e2e():
    wc = WC()
    cust = uid("C")
    flight = uid("F")
    hotel = uid("H")
    car = uid("R")

    xid_seed = wc.start()
    wc.addCustomer(xid_seed, cust)
    wc.addFlight(xid_seed, flight, PRICE, 3)
    wc.addHotel(xid_seed, hotel, PRICE, 2)
    wc.addCar(xid_seed, car, PRICE, 2)
    wc.commit(xid_seed)

    xid_resv = wc.start()
    wc.reserveFlight(xid_resv, cust, flight, seats=1)
    wc.reserveHotel(xid_resv, cust, hotel, rooms=1)
    wc.reserveCar(xid_resv, cust, car, cars=1)
    wc.commit(xid_resv)

    xid_q = wc.start()
    flight_rec = wc.queryFlight(xid_q, flight)
    hotel_rec = wc.queryHotel(xid_q, hotel)
    car_rec = wc.queryCar(xid_q, car)
    wc.commit(xid_q)

    assert flight_rec["numAvail"] == 2
    assert hotel_rec["numAvail"] == 1
    assert car_rec["numAvail"] == 1

    assert query_reservation(wc, cust, "FLIGHT", flight) is not None


# 业务失败（缺客户）要回滚，不产生副作用
def case_business_failure_rollback():
    wc = WC()
    flight = uid("FB")
    missing_customer = uid("NC")

    xid_seed = wc.start()
    wc.addFlight(xid_seed, flight, PRICE, 2)
    wc.commit(xid_seed)

    xid = wc.start()
    try:
        wc.reserveFlight(xid, missing_customer, flight, seats=1)
        raise AssertionError("reserveFlight should fail without customer")
    except Exception:
        wc.abort(xid)

    xid_q = wc.start()
    rec = wc.queryFlight(xid_q, flight)
    wc.commit(xid_q)

    assert rec is not None
    assert rec["numAvail"] == 2
    assert query_reservation(wc, missing_customer, "FLIGHT", flight) is None


# 并发预订不应超卖
def case_concurrent_reserve_no_oversell():
    wc = WC()
    cust = uid("CC")
    flight = uid("CR")

    xid_seed = wc.start()
    wc.addCustomer(xid_seed, cust)
    wc.addFlight(xid_seed, flight, PRICE, SEATS)
    wc.commit(xid_seed)

    results = []
    start = threading.Barrier(THREADS)

    def reserve_txn(wc, xid):
        tiny_sleep()
        wc.reserveFlight(xid, cust, flight, seats=1)

    threads = [
        threading.Thread(target=run_txn, args=(wc, reserve_txn, results, start))
        for _ in range(THREADS)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    committed = [r for r, _ in results if r == "commit"]

    xid_q = wc.start()
    rec = wc.queryFlight(xid_q, flight)
    wc.commit(xid_q)

    assert rec is not None
    assert rec["numAvail"] >= 0, f"numAvail < 0 ! {rec}"
    assert len(committed) <= SEATS, f"oversold! committed={len(committed)}, seats={SEATS}"


# deleteFlight 原子：abort 不删，commit 删除
def case_delete_atomicity():
    wc = WC()
    flight = uid("DA")

    xid = wc.start()
    wc.addFlight(xid, flight, PRICE, SEATS)
    wc.commit(xid)

    xid2 = wc.start()
    wc.deleteFlight(xid2, flight)
    wc.abort(xid2)

    xid3 = wc.start()
    rec = wc.queryFlight(xid3, flight)
    wc.commit(xid3)
    assert rec is not None, "delete aborted but flight missing"

    xid4 = wc.start()
    wc.deleteFlight(xid4, flight)
    wc.commit(xid4)

    xid5 = wc.start()
    rec = wc.queryFlight(xid5, flight)
    wc.commit(xid5)
    assert rec is None, "delete committed but flight still exists"


# prepare 冲突只允许一方成功
def case_prepare_conflict_propagation():
    wc = WC()
    cust = uid("PC")
    flight = uid("PF")

    xid_seed = wc.start()
    wc.addCustomer(xid_seed, cust)
    wc.addFlight(xid_seed, flight, PRICE, 1)
    wc.commit(xid_seed)

    results = []
    start = threading.Barrier(2)

    def reserve_one(wc, xid):
        tiny_sleep()
        wc.reserveFlight(xid, cust, flight, seats=1)

    threads = [
        threading.Thread(target=run_txn, args=(wc, reserve_one, results, start))
        for _ in range(2)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    committed = [r for r, _ in results if r == "commit"]

    xid_q = wc.start()
    rec = wc.queryFlight(xid_q, flight)
    wc.commit(xid_q)

    assert rec is not None
    assert rec["numAvail"] >= 0
    assert len(committed) <= 1, f"multiple commits on single seat: {results}"


# TM commit 幂等：重复 commit 不报错
def case_tm_commit_idempotent():
    wc = WC()
    flight = uid("IC")

    xid = wc.start()
    wc.addFlight(xid, flight, PRICE, 1)
    wc.commit(xid)
    wc.commit(xid)

    xid_q = wc.start()
    rec = wc.queryFlight(xid_q, flight)
    wc.commit(xid_q)
    assert rec is not None


# 并发 addFlight 仍保持唯一性
def case_concurrent_addFlight_unique():
    wc = WC()
    flight = uid("AF")

    results = []
    start = threading.Barrier(THREADS)

    def txn_body(wc, xid):
        tiny_sleep()
        wc.addFlight(xid, flight, PRICE, SEATS)

    threads = [
        threading.Thread(target=run_txn, args=(wc, txn_body, results, start))
        for _ in range(THREADS)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    committed = [r for r, _ in results if r == "commit"]
    assert len(committed) <= 1, f"multiple addFlight committed! {results}"


def run_all():
    cases = [
        case_happy_path_e2e,
        case_business_failure_rollback,
        case_concurrent_reserve_no_oversell,
        case_delete_atomicity,
        case_prepare_conflict_propagation,
        case_tm_commit_idempotent,
        case_concurrent_addFlight_unique,
    ]

    for case in cases:
        for i in range(ROUNDS):
            try:
                case()
            except Exception:
                print(f"\n❌ FAILED: {case.__name__}, round={i}")
                traceback.print_exc()
                return

    print("✅ ALL WC TESTS PASSED")


if __name__ == "__main__":
    run_all()
