import os
import time
import signal
import subprocess
import threading
import requests

from src.wc.workflow_controller import WC  # TODO: 按你项目真实路径修改


# =========================================================
# 与 start_service.py 100% 对齐的启动配置（用于 crash/restart）
# =========================================================

env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"

SERVICES = {
    "tm": {
        "app": "src.tm.transaction_manager:app",
        "port": "9001",
        "base": "http://127.0.0.1:9001",
        "health": "/health",
        "die": "/die",
    },
    "flight": {
        "app": "src.rms.service.flight_service:app",
        "port": "8001",
        "base": "http://127.0.0.1:8001",
        "health": "/health",
        "shutdown": "/shutdown",
    },
}

BASE_CMD = [
    "uvicorn",
    "--host", "0.0.0.0",
    "--log-level", "info",
]

HTTP_TIMEOUT = 2.0
PROCS: dict[str, subprocess.Popen] = {}


# =========================================================
# Proc helpers
# =========================================================

def _health_url(name: str) -> str:
    return SERVICES[name]["base"] + SERVICES[name]["health"]


def wait_health(name: str, timeout_sec: float = 15.0):
    url = _health_url(name)
    deadline = time.time() + timeout_sec
    last = None
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return
            last = f"status={r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(0.2)
    raise RuntimeError(f"[health] {name} not ready: {url}, last={last}")


def start_service(name: str):
    if name in PROCS and PROCS[name].poll() is None:
        return
    cfg = SERVICES[name]
    cmd = BASE_CMD + [cfg["app"], "--port", cfg["port"]]
    p = subprocess.Popen(
        cmd,
        cwd=os.getcwd(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    PROCS[name] = p
    wait_health(name)


def stop_service_soft(name: str):
    cfg = SERVICES[name]
    try:
        if name == "tm":
            requests.post(cfg["base"] + cfg["die"], timeout=HTTP_TIMEOUT)
        else:
            requests.post(cfg["base"] + cfg["shutdown"], timeout=HTTP_TIMEOUT)
    except Exception:
        pass
    time.sleep(0.5)


def stop_service_hard(name: str):
    p = PROCS.get(name)
    if not p:
        return
    try:
        p.send_signal(signal.SIGTERM)
    except Exception:
        pass
    try:
        p.wait(timeout=3)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    time.sleep(0.3)


def restart_service(name: str):
    stop_service_soft(name)
    stop_service_hard(name)
    start_service(name)


def ensure_up():
    start_service("tm")
    start_service("flight")


def shutdown_all():
    for n in ("flight", "tm"):
        try:
            stop_service_soft(n)
        except Exception:
            pass
        try:
            stop_service_hard(n)
        except Exception:
            pass


# =========================================================
# WC + API helpers
# =========================================================

def new_wc() -> WC:
    # 只测 flight 的 liveness，所以其它 rm url 随便填也行；
    # 但为了保持一致性，建议仍填全你的端口
    return WC(
        tm_url=SERVICES["tm"]["base"],
        flight_rm_url=SERVICES["flight"]["base"],
        hotel_rm_url="http://127.0.0.1:8002",
        car_rm_url="http://127.0.0.1:8003",
        customer_rm_url="http://127.0.0.1:8004",
        reservation_rm_url="http://127.0.0.1:8005",
    )


def uniq(prefix: str) -> str:
    return f"{prefix}{int(time.time() * 1000) % 100000}"


def expect(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def http_update_flight(xid: int, flight_num: str, updates: dict):
    """
    你 WC 没有 updateFlight，这里直接用 flight_rm 的 PUT /records/{key}
    """
    r = requests.put(
        f"{SERVICES['flight']['base']}/records/{flight_num}",
        json={"xid": xid, "updates": updates},
        timeout=HTTP_TIMEOUT,
    )
    return r


def rm_prepare(xid: int):
    """
    关键：直接让 RM 进入 PREPARED 并持锁悬挂
    """
    r = requests.post(
        f"{SERVICES['flight']['base']}/txn/prepare",
        json={"xid": xid},
        timeout=HTTP_TIMEOUT,
    )
    return r


def tm_start() -> int:
    r = requests.post(f"{SERVICES['tm']['base']}/txn/start", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()["xid"]


def tm_abort(xid: int):
    requests.post(
        f"{SERVICES['tm']['base']}/txn/abort",
        json={"xid": xid},
        timeout=HTTP_TIMEOUT,
    )


def tm_commit_raw(xid: int):
    return requests.post(
        f"{SERVICES['tm']['base']}/txn/commit",
        json={"xid": xid},
        timeout=HTTP_TIMEOUT,
    )


# =========================================================
# Level6 Tests
# =========================================================

def test_l6_prepared_blocks_write_but_not_forever():
    """
    L6-1A:
      - Txn A: update flight -> RM prepare (PREPARED, locks held)
      - Txn B: try update same flight and commit
      - Expect: B finishes quickly (fail/abort ok), not hang forever
    """
    print("\n[L6-1A] prepared blocks WRITE but system remains live")

    ensure_up()
    wc = new_wc()

    flight = uniq("F")

    # seed committed flight
    xid0 = wc.start()
    wc.addFlight(xid0, flight, price=100, numSeats=5)
    wc.commit(xid0)

    # Txn A: do an update so it enlists flight RM
    xid_a = tm_start()
    r = http_update_flight(xid_a, flight, {"price": 111})
    expect(r.status_code == 200, f"Txn A update failed: {r.status_code} {r.text}")

    # Force RM to PREPARED (locks held)
    pr = rm_prepare(xid_a)
    expect(pr.status_code == 200, f"RM prepare http failed: {pr.status_code} {pr.text}")
    expect(pr.json().get("ok") is True, f"RM prepare not ok: {pr.text}")

    # Txn B attempt in background, must not hang
    xid_b = tm_start()
    done = {"ok": False, "status": None, "err": None}

    def attempt_b():
        try:
            u = http_update_flight(xid_b, flight, {"price": 222})
            # update 可能返回 200，但 commit 阶段应该失败（锁冲突/版本冲突）
            cr = tm_commit_raw(xid_b)
            done["status"] = cr.status_code
            # ok 可能 True/False，关键是：不能卡死
            done["ok"] = True
        except Exception as e:
            done["err"] = str(e)
            done["ok"] = True

    t = threading.Thread(target=attempt_b, daemon=True)
    t.start()
    t.join(timeout=3.0)

    expect(done["ok"], "Txn B hung >3s under PREPARED lock (liveness violation)")

    # cleanup: abort A to release locks
    tm_abort(xid_a)

    print("  -> PASS")
    return True


def test_l6_read_not_blocked_by_prepared_write():
    """
    L6-1B:
      - Txn A: update -> PREPARED (uncommitted)
      - Txn R: read should return quickly
      - Prefer: read sees old committed value (100), not the uncommitted (111)
    """
    print("\n[L6-1B] READ should not hang under PREPARED WRITE (and should see committed data)")

    ensure_up()
    wc = new_wc()

    flight = uniq("F")

    # seed committed
    xid0 = wc.start()
    wc.addFlight(xid0, flight, price=100, numSeats=5)
    wc.commit(xid0)

    # Txn A: update then prepare (hold locks)
    xid_a = tm_start()
    r = http_update_flight(xid_a, flight, {"price": 111})
    expect(r.status_code == 200, f"Txn A update failed: {r.status_code} {r.text}")

    pr = rm_prepare(xid_a)
    expect(pr.status_code == 200, f"RM prepare http failed: {pr.status_code} {pr.text}")
    expect(pr.json().get("ok") is True, f"RM prepare not ok: {pr.text}")

    # Txn R: read should return quickly
    xid_r = wc.start()
    out = {"done": False, "rec": None, "err": None}

    def do_read():
        try:
            rec = wc.queryFlight(xid_r, flight)
            out["rec"] = rec
        except Exception as e:
            out["err"] = str(e)
        finally:
            out["done"] = True

    t = threading.Thread(target=do_read, daemon=True)
    t.start()
    t.join(timeout=2.0)

    expect(out["done"], "READ hung under PREPARED (bad liveness for reads)")
    expect(out["rec"] is not None, f"READ failed unexpectedly: {out['err']}")

    # 常见语义：读到 committed 值（100），不读到 A 的未提交 111
    expect(out["rec"]["price"] == 100, f"READ saw uncommitted data? price={out['rec']['price']}")

    # cleanup
    tm_abort(xid_a)

    print("  -> PASS")
    return True


def test_l6_release_after_abort_allows_progress():
    """
    L6-1C:
      - Txn A: PREPARED hold lock
      - Txn B: commit fails (or at least can't succeed)
      - Abort A: release lock
      - Txn C: same write+commit should succeed quickly
    """
    print("\n[L6-1C] after ABORT prepared txn, other txns should proceed")

    ensure_up()
    wc = new_wc()

    flight = uniq("F")

    # seed committed
    xid0 = wc.start()
    wc.addFlight(xid0, flight, price=100, numSeats=5)
    wc.commit(xid0)

    # A prepared
    xid_a = tm_start()
    r = http_update_flight(xid_a, flight, {"price": 111})
    expect(r.status_code == 200, f"A update failed: {r.status_code} {r.text}")
    pr = rm_prepare(xid_a)
    expect(pr.json().get("ok") is True, f"A prepare failed: {pr.text}")

    # B try commit quickly
    xid_b = tm_start()
    http_update_flight(xid_b, flight, {"price": 222})
    b = tm_commit_raw(xid_b)
    # 允许 200/409/ok false，各实现不同；关键是：现在还没释放，B 不该“悄悄成功改变数据”
    # 我们不在这一步断言强语义，只记录一下：
    # print("  B commit status:", b.status_code, b.text[:120])

    # abort A -> release
    tm_abort(xid_a)

    # C should succeed
    xid_c = tm_start()
    u = http_update_flight(xid_c, flight, {"price": 333})
    expect(u.status_code == 200, f"C update failed: {u.status_code} {u.text}")

    c = tm_commit_raw(xid_c)
    # TM commit 成功的典型返回：200 {"ok": true}
    expect(c.status_code == 200, f"C commit http failed: {c.status_code} {c.text}")
    expect(c.json().get("ok") is True, f"C commit not ok: {c.text}")

    # verify final price is 333
    xid_v = wc.start()
    rec = wc.queryFlight(xid_v, flight)
    expect(rec is not None, "verification read failed")
    expect(rec["price"] == 333, f"expected price=333 got {rec['price']}")

    print("  -> PASS")
    return True


def test_l6_prepared_then_crash_rm_unlocks_after_restart():
    """
    L6-1D（很有价值）:
      - Txn A prepared 持锁
      - crash flight RM + restart
      - 期望：锁不会永久遗留（否则全系统锁死）
      - 然后 Txn B 能成功 commit

    这个测试要求：RM 重启后必须清理锁/悬挂状态（或从持久化恢复并可被 abort/commit）
    """
    print("\n[L6-1D] prepared lock should not be permanent across RM crash/restart")

    ensure_up()
    wc = new_wc()

    flight = uniq("F")

    # seed committed
    xid0 = wc.start()
    wc.addFlight(xid0, flight, price=100, numSeats=5)
    wc.commit(xid0)

    # A prepared
    xid_a = tm_start()
    r = http_update_flight(xid_a, flight, {"price": 111})
    expect(r.status_code == 200, f"A update failed: {r.status_code} {r.text}")
    pr = rm_prepare(xid_a)
    expect(pr.json().get("ok") is True, f"A prepare failed: {pr.text}")

    # crash + restart flight RM
    restart_service("flight")

    # now try a new txn B to update+commit
    xid_b = tm_start()
    u = http_update_flight(xid_b, flight, {"price": 222})
    expect(u.status_code == 200, f"B update failed after restart: {u.status_code} {u.text}")

    b = tm_commit_raw(xid_b)
    # 如果 RM 重启后锁遗留，B 会一直失败或卡住；我们要求它能成功
    expect(b.status_code == 200, f"B commit http failed: {b.status_code} {b.text}")
    expect(b.json().get("ok") is True, f"B commit not ok: {b.text}")

    xid_v = wc.start()
    rec = wc.queryFlight(xid_v, flight)
    expect(rec["price"] == 222, f"expected price=222 got {rec['price']}")

    print("  -> PASS")
    return True


# =========================================================
# Runner
# =========================================================

def run_level6():
    tests = [
        test_l6_prepared_blocks_write_but_not_forever,
        test_l6_read_not_blocked_by_prepared_write,
        test_l6_release_after_abort_allows_progress,
        test_l6_prepared_then_crash_rm_unlocks_after_restart,
    ]

    passed = 0
    try:
        for t in tests:
            try:
                if t():
                    passed += 1
            except Exception as e:
                print("  -> FAIL:", e)
        print(f"\nLEVEL6 RESULT: {passed}/{len(tests)} passed")
    finally:
        shutdown_all()


if __name__ == "__main__":
    run_level6()
