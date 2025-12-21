import time
import requests
import subprocess
import os

TM = "http://127.0.0.1:9001"
RM = "http://127.0.0.1:8001"

env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"

def wait_health(url, timeout=10):
    for _ in range(timeout * 10):
        try:
            r = requests.get(f"{url}/health", timeout=0.5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"{url} not healthy")


# -------------------------
# TM helpers
# -------------------------

def start_txn():
    r = requests.post(f"{TM}/txn/start")
    r.raise_for_status()
    return r.json()["xid"]


def enlist(xid):
    r = requests.post(
        f"{TM}/txn/enlist",
        json={"xid": xid, "rm": RM},
    )
    r.raise_for_status()


def tm_commit(xid):
    r = requests.post(f"{TM}/txn/commit", json={"xid": xid})
    r.raise_for_status()
    return r.json()


# -------------------------
# RM helpers (Flight)
# -------------------------

def rm_insert_flight(xid, flight_num, price, seats):
    r = requests.post(
        f"{RM}/records",
        json={
            "xid": xid,
            "record": {
                "flightNum": flight_num,
                "price": price,
                "numSeats": seats,
                "numAvail": seats,
            },
        },
    )
    r.raise_for_status()
    return r.json()


def rm_read_flight(xid, flight_num):
    r = requests.get(
        f"{RM}/records/{flight_num}",
        params={"xid": xid},
    )
    r.raise_for_status()
    return r.json()


def rm_shutdown():
    try:
        requests.post(f"{RM}/shutdown", timeout=0.2)
    except Exception:
        pass  # expected


# -------------------------
# Test
# -------------------------

def test_crash_after_prepare():
    print("== wait services ==")
    wait_health(TM)
    wait_health(RM)

    print("== start txn ==")
    xid = start_txn()
    enlist(xid)

    print("== insert flight record ==")
    rm_insert_flight(
        xid,
        flight_num="MU1001",
        price=1200,
        seats=180,
    )

    print("== commit (RM will crash after prepare) ==")
    try:
        tm_commit(xid)
    except Exception:
        pass  # expected because RM crashes

    print("== wait RM restart & recover ==")
    wait_health(RM)

    print("== retry commit ==")
    res = tm_commit(xid)
    assert res["ok"] is True

    print("== verify committed data ==")
    xid2 = start_txn()
    enlist(xid2)

    rec = rm_read_flight(xid2, "MU1001")
    assert rec["ok"] is True
    assert rec["value"]["price"] == 1200
    assert rec["value"]["numAvail"] == 180

    print("✅ test passed: Flight RM recovered after prepare crash")


if __name__ == "__main__":
    test_crash_after_prepare()
