import threading
import random
import time
import traceback

from src.wc.workflow_controller import FlightWC   # ← 您给的那个类

# =========================
# 配置
# =========================

THREADS = 8
ROUNDS = 200
SLEEP_MAX = 0.005

FLIGHT = "MU10"
PRICE = 500
SEATS = 5


# =========================
# 工具
# =========================

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
    except Exception as e:
        if xid is not None:
            wc.abort(xid)
        results.append(("abort", xid))


# =========================
# Case 1：并发 addFlight（唯一性）
# =========================

def case_concurrent_addFlight():
    wc = FlightWC()

    results = []
    start = threading.Barrier(THREADS)

    def txn_body(wc, xid):
        tiny_sleep()
        wc.addFlight(xid, FLIGHT, PRICE, SEATS)

    threads = [
        threading.Thread(target=run_txn, args=(wc, txn_body, results, start))
        for _ in range(THREADS)
    ]

    for t in threads: t.start()
    for t in threads: t.join()

    committed = [r for r, _ in results if r == "commit"]

    assert len(committed) <= 1, f"multiple addFlight committed! {results}"


# =========================
# Case 2：Abort 不可见
# =========================

def case_abort_visibility():
    wc = FlightWC()

    xid = wc.start()
    wc.addFlight(xid, FLIGHT, PRICE, SEATS)
    wc.abort(xid)

    xid2 = wc.start()
    rec = wc.queryFlight(xid2, FLIGHT)
    wc.commit(xid2)

    assert rec is None, f"abort flight visible! {rec}"


# =========================
# Case 3：并发 reserveFlight（不超卖）
# =========================

def case_concurrent_reserve():
    wc = FlightWC()

    # init flight
    # xid = wc.start()
    # wc.addFlight(xid, FLIGHT, PRICE, SEATS)
    # wc.commit(xid)

    results = []
    start = threading.Barrier(THREADS)

    def reserve_txn(wc, xid):
        tiny_sleep()
        wc.reserveFlight(xid, FLIGHT, seats=1)

    threads = [
        threading.Thread(target=run_txn, args=(wc, reserve_txn, results, start))
        for _ in range(THREADS)
    ]

    for t in threads: t.start()
    for t in threads: t.join()

    committed = len([r for r, _ in results if r == "commit"])

    xidq = wc.start()
    rec = wc.queryFlight(xidq, FLIGHT)
    wc.commit(xidq)

    assert rec is not None
    assert rec["numAvail"] >= 0, f"numAvail < 0 ! {rec}"
    assert committed <= SEATS, f"oversold! committed={committed}, seats={SEATS}"


# =========================
# Case 4：deleteFlight 原子性
# =========================

def case_delete_atomicity():
    wc = FlightWC()

    # init
    xid = wc.start()
    wc.addFlight(xid, FLIGHT, PRICE, SEATS)
    wc.commit(xid)

    # delete abort
    xid2 = wc.start()
    wc.deleteFlight(xid2, FLIGHT)
    wc.abort(xid2)

    xid3 = wc.start()
    rec = wc.queryFlight(xid3, FLIGHT)
    wc.commit(xid3)

    assert rec is not None, "delete aborted but flight missing"

    # delete commit
    xid4 = wc.start()
    wc.deleteFlight(xid4, FLIGHT)
    wc.commit(xid4)

    xid5 = wc.start()
    rec = wc.queryFlight(xid5, FLIGHT)
    wc.commit(xid5)

    assert rec is None, "delete committed but flight still exists"


# =========================
# 主入口
# =========================

def run_all():
    cases = [
        # case_concurrent_addFlight,
        # case_abort_visibility,
        # case_concurrent_reserve,
        case_delete_atomicity,
    ]

    for case in cases:
        for i in range(ROUNDS):
            try:
                case()
            except Exception:
                print(f"\n❌ FAILED: {case.__name__}, round={i}")
                traceback.print_exc()
                return

    print("✅ ALL FlightWC CONCURRENCY TESTS PASSED")


if __name__ == "__main__":
    run_all()
