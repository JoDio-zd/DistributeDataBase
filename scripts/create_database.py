import os
import subprocess
from typing import Dict

# ======================
# Global Config
# ======================

MYSQL_IMAGE = "mysql:oraclelinux9"
MYSQL_ROOT_PASSWORD = "1234"

BASE_PORT = 33061
BASE_DATA_DIR = "./data"
BASE_INIT_DIR = "./scripts/db-init"

# ======================
# RM Definitions
# ======================

RMS: Dict[str, Dict] = {
    "flight": {
        "port": 33061,
        "init_dir": "flight",
    },
    "hotel": {
        "port": 33062,
        "init_dir": "hotel",
    },
    "car": {
        "port": 33063,
        "init_dir": "car",
    },
    "customer": {
        "port": 33064,
        "init_dir": "customer",
    },
}

# ======================
# Utils
# ======================

def run(cmd: list[str]):
    print(">>", " ".join(cmd))
    subprocess.run(cmd, check=True)


def remove_container_if_exists(name: str):
    subprocess.run(
        ["docker", "rm", "-f", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ======================
# Main Logic
# ======================

def start_mysql_rm(rm_name: str, cfg: Dict):
    container_name = f"mysql-{rm_name}"

    data_dir = os.path.join(BASE_DATA_DIR, container_name)
    init_dir = os.path.join(BASE_INIT_DIR, cfg["init_dir"])

    os.makedirs(data_dir, exist_ok=True)

    if not os.path.isdir(init_dir):
        raise RuntimeError(f"Init SQL directory not found: {init_dir}")

    remove_container_if_exists(container_name)

    run([
        "docker", "run", "-d",
        "--name", container_name,
        "-e", f"MYSQL_ROOT_PASSWORD={MYSQL_ROOT_PASSWORD}",
        "-p", f"{cfg['port']}:3306",
        "-v", f"{os.path.abspath(data_dir)}:/var/lib/mysql",
        "-v", f"{os.path.abspath(init_dir)}:/docker-entrypoint-initdb.d",
        MYSQL_IMAGE
    ])

    print(f"✅ {container_name} started at localhost:{cfg['port']}")


def main():
    os.makedirs(BASE_DATA_DIR, exist_ok=True)

    print("🚀 Starting MySQL DBS cluster...\n")

    for rm_name, cfg in RMS.items():
        start_mysql_rm(rm_name, cfg)

    print("\n🎉 All DBS instances are up.")
    print("\n📌 Ports:")
    for rm_name, cfg in RMS.items():
        print(f"  mysql-{rm_name}: localhost:{cfg['port']}")


if __name__ == "__main__":
    main()
