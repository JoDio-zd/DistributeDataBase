import time
import subprocess
import requests
import os
import signal

from src.wc.workflow_controller import WC   # ← 按你项目真实路径改


# =========================================================
# Config（与你 start_service.py 完全一致）
# =========================================================

TM_URL = "http://127.0.0.1:9001"

RM_CFG = {
    "flight": {
        "url": "http://127.0.0.1:8001",
        "app": "src.rms.service.flight_service:app",
        "port": "8001",
    },
    "hotel": {
        "url": "http://127.0.0.1:8002",
        "app": "src.rms.service.hotel_service:app",
        "port": "8002",
    },
    "car": {
        "url": "http://127.0.0.1:8003",
        "app": "src.rms.service.car_service:app",
        "port": "8003",
    },
    "customer": {
        "url": "http://127.0.0.1:8004",
        "app": "src.rms.service.customer_service:app",
        "port": "8004",
    },
    "reservation": {
        "url": "http://127.0.0.1:8005",
        "app": "src.rms.service.reservation_service:app",
        "port": "8005",
    },
}

BASE_CMD = [
    "uvicorn",
    "--host", "0.0.0.0",
    "--log-level", "info",
]

ENV = os.environ.copy()
ENV["PYTHONUNBUFFERED"] = "1"

HTTP_TIMEOUT = 2.0


# =========================================================
# Helpers
# =========================================================

def uniq(prefix):
    return f"{prefix}{int(time.time() * 1000) % 100000}"


def wait_health(url, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/health", timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"health check failed: {url}")


def crash_rm(name):
    url = RM_CFG[name]["url"]
    print(f"  -> crash {name}")
    try:
        requests.post(f"{url}/shutdown", timeout=HTTP_TIMEOUT)
    except Exception:
        pass
    time.sleep(0.5)


def restart_rm(name):
    cfg = RM_CFG[name]

    cmd = BASE_CMD + [
        cfg["app"],
        "--port", cfg["port"],
    ]

    print(f"  -> restart {name}")
    proc = subprocess.Popen(
        cmd,
        cwd=os.getcwd(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=ENV,
    )

    wait_health(cfg["url"])
    return proc


def new_wc():
    return WC(
        tm_url=TM_URL,
        flight_rm_url=RM_CFG["flight"]["url"],
        hotel_rm_url=RM_CFG["hotel"]["url"],
        car_rm_url=RM_CFG["car"]["url"],
        customer_rm_url=RM_CFG["customer"]["url"],
        reservation_rm_url=RM_CFG["reservation"]["url"],
    )


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


# =========================================================
# Level4 Tests
# =========================================================

def test_l4_commit_then_crash_and_restart():
    """
    commit → crash → restart
    => 数据必须存在（Durability）
    """
    print("\n[L4] commit → crash → restart")

    wc = new_wc()
    flight = uniq("F")

    xid = wc.start()
    wc.addFlight(xid, flight, price=500, numSeats=3)
    wc.commit(xid)

    crash_rm("flight")
    restart_rm("flight")

    wc2 = new_wc()
    xid2 = wc2.start()
    rec = wc2.queryFlight(xid2, flight)

    expect(rec is not None, "flight missing after restart")
    expect(rec["price"] == 500, f"expected 500, got {rec.get('price')}")

    print("  -> PASS")
    return True


def test_l4_abort_then_crash_and_restart():
    """
    abort → crash → restart
    => 数据必须不存在（Atomicity）
    """
    print("\n[L4] abort → crash → restart")

    wc = new_wc()
    flight = uniq("F")

    xid = wc.start()
    wc.addFlight(xid, flight, price=123, numSeats=1)
    wc.abort(xid)

    crash_rm("flight")
    restart_rm("flight")

    wc2 = new_wc()
    xid2 = wc2.start()
    rec = wc2.queryFlight(xid2, flight)

    expect(rec is None, "aborted flight should not exist")

    print("  -> PASS")
    return True


def test_l4_reserve_atomicity_with_restart():
    """
    reserveFlight = flight(numAvail--) + reservation(insert)
    crash before commit → restart
    => numAvail 不变
    """
    print("\n[L4] reserve atomicity with restart")

    wc = new_wc()
    cust = uniq("C")
    flight = uniq("F")

    xid0 = wc.start()
    wc.addCustomer(xid0, cust)
    wc.addFlight(xid0, flight, price=200, numSeats=1)
    wc.commit(xid0)

    xid = wc.start()
    wc.reserveFlight(xid, cust, flight)

    crash_rm("reservation")
    restart_rm("reservation")

    wc.abort(xid)

    wc2 = new_wc()
    xid2 = wc2.start()
    f = wc2.queryFlight(xid2, flight)

    expect(f["numAvail"] == 1, f"numAvail corrupted: {f['numAvail']}")

    print("  -> PASS")
    return True


# =========================================================
# Runner
# =========================================================

def run_level4():
    tests = [
        test_l4_commit_then_crash_and_restart,
        test_l4_abort_then_crash_and_restart,
        test_l4_reserve_atomicity_with_restart,
    ]

    passed = 0
    for t in tests:
        try:
            if t():
                passed += 1
        except Exception as e:
            print("  -> FAIL:", e)

    print(f"\nLEVEL4 RESULT: {passed}/{len(tests)} passed")


if __name__ == "__main__":
    run_level4()
