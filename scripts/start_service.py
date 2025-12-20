import subprocess
import os
import sys

cmd0 = [
    "uvicorn",
    "src.tm.transaction_manager:app",
    "--host",
    "0.0.0.0",
    "--port",
    "9001",
    "--reload",
]

cmd1 = [
    "uvicorn",
    "src.rms.service.flight_service:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8001",
    "--reload",
]

cmd2 = [
    "uvicorn",
    "src.rms.service.hotel_service:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8002",
    "--reload",
]

cmd3 = [
    "uvicorn",
    "src.rms.service.car_service:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8003",
    "--reload",
]

cmd4 = [
    "uvicorn",
    "src.rms.service.customer_service:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8004",
    "--reload",
]


def a0():
    subprocess.run(cmd0, cwd=os.getcwd())


def a1():
    subprocess.run(cmd1, cwd=os.getcwd())


def a2():
    subprocess.run(cmd2, cwd=os.getcwd())


def a3():
    subprocess.run(cmd3, cwd=os.getcwd())


def a4():
    subprocess.run(cmd4, cwd=os.getcwd())


if __name__ == "__main__":
    if sys.argv[1] == "0":
        a0()
    elif sys.argv[1] == "1":
        a1()
    elif sys.argv[1] == "2":
        a2()
    elif sys.argv[1] == "3":
        a3()
    elif sys.argv[1] == "4":
        a4()
