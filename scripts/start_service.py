import subprocess
import os
import sys
import threading
import time
import signal

# =========================
# 环境变量（关键）
# =========================
env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"

# =========================
# 颜色配置
# =========================
COLORS = {
    "tm": "\033[95m",          # 紫
    "flight": "\033[94m",      # 蓝
    "hotel": "\033[96m",       # 青
    "car": "\033[92m",         # 绿
    "customer": "\033[93m",    # 黄
    "reservation": "\033[91m", # 红
    "reset": "\033[0m",
}

# =========================
# 服务配置
# =========================
SERVICES = {
    "tm": {
        "app": "src.tm.transaction_manager:app",
        "port": "9001",
    },
    "flight": {
        "app": "src.rms.service.flight_service:app",
        "port": "8001",
    },
    "hotel": {
        "app": "src.rms.service.hotel_service:app",
        "port": "8002",
    },
    "car": {
        "app": "src.rms.service.car_service:app",
        "port": "8003",
    },
    "customer": {
        "app": "src.rms.service.customer_service:app",
        "port": "8004",
    },
    "reservation": {
        "app": "src.rms.service.reservation_service:app",
        "port": "8005",
    },
}

BASE_CMD = [
    "uvicorn",
    "--host", "0.0.0.0",
    "--log-level", "info",
    # 不开 reload，避免子进程干扰日志
]

# =========================
# 启动单个服务
# =========================
def start_service(name):
    cfg = SERVICES[name]
    color = COLORS.get(name, "")
    reset = COLORS["reset"]

    cmd = BASE_CMD + [
        cfg["app"],
        "--port", cfg["port"],
    ]

    print(f"{color}[START] {name:<12} → {cfg['port']}{reset}")

    proc = subprocess.Popen(
        cmd,
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    return proc, name


# =========================
# 日志读取线程（关键）
# =========================
def stream_logs(proc, name):
    color = COLORS.get(name, "")
    reset = COLORS["reset"]

    try:
        for line in proc.stdout:
            print(f"{color}[{name.upper():<11}] {line.rstrip()}{reset}")
    except Exception as e:
        print(f"[{name}] log stream error: {e}")


# =========================
# 启动多个服务
# =========================
def start_many(names):
    procs = []

    try:
        for name in names:
            p, svc = start_service(name)
            procs.append((p, svc))

            t = threading.Thread(
                target=stream_logs,
                args=(p, svc),
                daemon=True,
            )
            t.start()

        print("\nAll services started. Ctrl+C to stop.\n")

        # 主线程只负责活着
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping all services...")

    finally:
        for p, _ in procs:
            try:
                p.send_signal(signal.SIGTERM)
            except Exception:
                pass

        for p, _ in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()

        print("All services stopped.")


# =========================
# CLI 入口
# =========================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "up"

    if mode == "up":
        start_many(SERVICES.keys())
    elif mode == "rm":
        start_many(k for k in SERVICES if k != "tm")
    elif mode in SERVICES:
        start_many([mode])
    else:
        print("Usage:")
        print("  python start_service.py up")
        print("  python start_service.py rm")
        print("  python start_service.py tm|flight|hotel|car|customer|reservation")
