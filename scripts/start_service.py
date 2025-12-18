import subprocess
import os
import sys

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
    "src.tm.transaction_manager:app",
    "--host",
    "0.0.0.0",
    "--port",
    "9000",
    "--reload",
]
def a1():
    subprocess.run(cmd1, cwd=os.getcwd())

def a2():
    subprocess.run(cmd2, cwd=os.getcwd())

if __name__ == "__main__":
    if sys.argv[1] == "1":
        a1()
    elif sys.argv[1] == "2":
        a2()