import os
import time
import signal
import subprocess
import threading
import requests

from src.wc.workflow_controller import WC  # ← 按您项目实际路径改


# =========================================================
# 与 start_service.py 100% 对齐的启动配置
# =========================================================

env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"

SERVICES = {
    "tm": {
        "app": "src.tm.transaction_manager:app",
        "port": "9001",
        "base": "http://127.0.0.1:9001",
        "die": "/die",
        "health": "/health",
    },
    "flight": {
        "app": "src.rms.service.flight_service:app",
        "port": "8001",
        "base": "http://127.0.0.1:8001",
        "shutdown": "/shutdown",
        "health": "/health",
    },
    "hotel": {
        "app": "src.rms.service.hotel_service:app",
        "port": "8002",
        "base": "http://127.0.0.1:8002",
        "shutdown": "/shutdown",
        "health": "/health",
    },
    "car": {
        "app": "src.rms.service.car_service:app",
        "port": "8003",
        "base": "http://127.0.0.1:8003",
        "shutdown": "/shutdown",
        "health": "/health",
    },
    "customer": {
        "app": "src.rms.service.customer_service:app",
        "port": "8004",
        "base": "http://127.0.0.1:8004",
        "shutdown": "/shutdown",
        "health": "/health",
    },
    "reservation": {
        "app": "src.rms.service.reservation_service:app",
        "port": "8005",
        "base": "http://127.0.0.1:8005",
        "shutdown": "/shutdown",
        "health": "/health",
    },
}

BASE_CMD = [
    "uvicorn",
    "--host", "0.0.0.0",
    "--log-level", "info",
]

HTTP_TIMEOUT = 2.0


# =========================================================
# Proc manager
# =========================================================

PROCS: dict[str, subprocess.Popen] = {}


def _health_url(name: str) -> str:
    return SERVICES[name]["base"] + SERVICES[name]["health"]


def wait_health(name: str, timeout_sec: float = 15.0):
    deadline = time.time() + timeout_sec
    last = None
    url = _health_url(name)
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return
            last = f"status={r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(0.2)
    raise RuntimeError(f"[health] {name} not ready: {url} last={last}")


def start_service(name: str):
    if name in PROCS and PROCS[name].poll() is None:
        return
    cfg = SERVICES[name]
    cmd = BASE_CMD + [
        cfg["app"],
        "--port", cfg["port"],
    ]
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
        p.wait(timeout=2)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    time.sleep(0.5)


def restart_service(name: str):
    # soft first
    stop_service_soft(name)
    # then ensure dead
    stop_service_hard(name)
    start_service(name)


def ensure_all_up():
    # TM first
    start_service("tm")
    for n in ("flight", "hotel", "car", "customer", "reservation"):
        start_service(n)


def shutdown_all():
    for n in ("reservation", "customer", "car", "hotel", "flight", "tm"):
        try:
            stop_service_soft(n)
        except Exception:
            pass
        try:
            stop_service_hard(n)
        except Exception:
            pass


# =========================================================
# WC + business helpers
# =========================================================

def new_wc() -> WC:
    return WC(
        tm_url=SERVICES["tm"]["base"],
        flight_rm_url=SERVICES["flight"]["base"],
        hotel_rm_url=SERVICES["hotel"]["base"],
        car_rm_url=SERVICES["car"]["base"],
        customer_rm_url=SERVICES["customer"]["base"],
        reservation_rm_url=SERVICES["reservation"]["base"],
    )


def uniq(prefix: str) -> str:
    return f"{prefix}{int(time.time() * 1000) % 100000}"


def expect(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def make_big_multi_rm_txn(wc: WC, xid: int, cust: str, flight: str, hotel: str, car: str):
    """
    让 prepare/commit 路径更“长”，提高 failpoint timing 的稳定性。
    这里做多参与者 + 多次写：customer / flight / hotel / car / reservation
    """
    wc.addCustomer(xid, cust)

    wc.addFlight(xid, flight, price=500, numSeats=2)
    wc.addHotel(xid, hotel, price=300, numRooms=2)
    wc.addCar(xid, car, price=200, numCars=2)

    # reserve 三样东西：会写 flight/hotel/car + reservation（三条）
    wc.reserveFlight(xid, cust, flight)
    wc.reserveHotel(xid, cust, hotel)
    wc.reserveCar(xid, cust, car)


def query_snapshot(wc: WC, xid: int, cust: str, flight: str, hotel: str, car: str):
    """
    WC 视角读回关键不变式：
    - flight/hotel/car 的 numAvail
    - 这些对象是否存在
    """
    f = wc.queryFlight(xid, flight)
    h = wc.queryHotel(xid, hotel)
    c = wc.queryCar(xid, car)
    u = wc.queryCustomer(xid, cust)
    return u, f, h, c


# =========================================================
# Level5 Tests
# =========================================================

def test_l5_tm_crash_during_commit_then_restart_and_retry():
    """
    Level5-1（最核心）：
      - 多 RM txn
      - 发起 TM /txn/commit 的过程中把 TM 杀掉（模拟崩溃）
      - 重启 TM
      - 客户端重试 commit / abort
      - 最终外部世界必须“收敛”到一种一致结果（要么全有、要么全无）

    ⚠️ 重要现实：
      如果您 TM 还没有 decision log（持久化事务 & 决议），那么 TM 重启后会丢 transactions[xid]，
      这条测试会 FAIL（commit 404）——这正是 Level5 要你补的东西。
    """
    print("\n[L5] TM crash during commit -> restart -> retry (in-doubt)")

    ensure_all_up()
    wc = new_wc()

    cust = uniq("C")
    flight = uniq("F")
    hotel = uniq("H")
    car = uniq("R")

    xid = wc.start()
    make_big_multi_rm_txn(wc, xid, cust, flight, hotel, car)

    # 用 thread 发起 commit（让我们能在中途杀 TM）
    commit_result = {"ok": None, "err": None}

    def do_commit():
        try:
            wc.commit(xid)
            commit_result["ok"] = True
        except Exception as e:
            commit_result["ok"] = False
            commit_result["err"] = str(e)

    t = threading.Thread(target=do_commit, daemon=True)
    t.start()

    # 给 commit 进入 prepare/commit 一点时间
    time.sleep(0.3)

    # 强杀 TM（更像真实 crash）
    stop_service_hard("tm")

    # 等 commit thread 收尾
    t.join(timeout=3)

    # 重启 TM
    start_service("tm")

    # 现在“正确系统”应该允许客户端重试：commit 或 abort 都能让事务收敛
    # 我们做两步：
    #  1) retry commit（如果 TM 有 decision log，应返回 200/409）
    #  2) 再查外部世界是否一致
    r = requests.post(
        SERVICES["tm"]["base"] + "/txn/commit",
        json={"xid": xid},
        timeout=HTTP_TIMEOUT,
    )

    # 如果这里是 404，说明 TM 重启丢事务：Level5 的缺口就是 decision log
    if r.status_code == 404:
        raise AssertionError(
            "TM restart lost xid (404). Level5 requires decision log / txn persistence in TM."
        )

    expect(r.status_code in (200, 409), f"unexpected TM commit retry status={r.status_code}")

    # 外部状态一致性检查：要么全部对象存在且 numAvail=1（因为 reserve 三次扣了 1）
    # 要么全都不存在（如果最终决议是 ABORT）
    xid2 = wc.start()
    u, f, h, c = query_snapshot(wc, xid2, cust, flight, hotel, car)

    all_exist = (u is not None and f is not None and h is not None and c is not None)
    none_exist = (u is None and f is None and h is None and c is None)

    expect(all_exist or none_exist, "inconsistent world: partial commit observed")

    if all_exist:
        expect(f["numAvail"] == 1, f"flight numAvail expected 1 got {f['numAvail']}")
        expect(h["numAvail"] == 1, f"hotel numAvail expected 1 got {h['numAvail']}")
        expect(c["numAvail"] == 1, f"car numAvail expected 1 got {c['numAvail']}")

    print("  -> PASS")
    return True


def test_l5_rm_crash_after_prepare_before_commit_then_recover_with_retry():
    """
    Level5-2（经典不对称失败）：
      - commit 过程中，RM 在 commit 阶段崩溃（prepare 已经 ok）
      - 重启 RM
      - TM / client 重试 commit
      - 最终一致（不能半条业务）

    实现手段（不改你 TM 代码）：
      - 我们在 commit 开始后，延迟一点点再杀掉某个 RM（reservation），提高“落在 commit 阶段”的概率
      - 这是 failpoint timing，稳定性取决于事务规模（我们用 big txn 拉长路径）
    """
    print("\n[L5] RM crash after prepare (likely) -> restart -> retry commit")

    ensure_all_up()
    wc = new_wc()

    cust = uniq("C")
    flight = uniq("F")
    hotel = uniq("H")
    car = uniq("R")

    xid = wc.start()
    make_big_multi_rm_txn(wc, xid, cust, flight, hotel, car)

    # commit in background
    commit_done = {"done": False}

    def do_commit():
        try:
            requests.post(
                SERVICES["tm"]["base"] + "/txn/commit",
                json={"xid": xid},
                timeout=10,  # 让 commit 线程尽量跑久一点
            )
        finally:
            commit_done["done"] = True

    t = threading.Thread(target=do_commit, daemon=True)
    t.start()

    # 给 TM 先走到 prepare（大概率），然后杀 reservation RM（希望落在 commit 阶段）
    time.sleep(0.6)
    stop_service_hard("reservation")

    # 等 commit 返回（不要求成功）
    t.join(timeout=12)

    # 重启 reservation
    start_service("reservation")

    # 重试 commit（正确系统：应最终收敛为 COMMIT）
    r = requests.post(
        SERVICES["tm"]["base"] + "/txn/commit",
        json={"xid": xid},
        timeout=HTTP_TIMEOUT,
    )

    # 同理，如果 TM 没有 decision log，有可能 404
    if r.status_code == 404:
        raise AssertionError(
            "TM restart/loss of xid (404). Level5 needs decision log / recovery."
        )

    expect(r.status_code in (200, 409), f"unexpected commit retry status={r.status_code}")

    # 外部一致性检查（全有 or 全无）
    xid2 = wc.start()
    u, f, h, c = query_snapshot(wc, xid2, cust, flight, hotel, car)

    all_exist = (u is not None and f is not None and h is not None and c is not None)
    none_exist = (u is None and f is None and h is None and c is None)
    expect(all_exist or none_exist, "partial commit observed after RM crash/retry")

    print("  -> PASS")
    return True


# =========================================================
# Runner
# =========================================================

def run_level5():
    tests = [
        test_l5_tm_crash_during_commit_then_restart_and_retry,
        test_l5_rm_crash_after_prepare_before_commit_then_recover_with_retry,
    ]

    passed = 0
    try:
        for t in tests:
            try:
                if t():
                    passed += 1
            except Exception as e:
                print("  -> FAIL:", e)
        print(f"\nLEVEL5 RESULT: {passed}/{len(tests)} passed")
    finally:
        shutdown_all()


if __name__ == "__main__":
    run_level5()
