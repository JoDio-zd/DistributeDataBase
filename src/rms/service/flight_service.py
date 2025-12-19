# src/rms/flight_rm_service.py
from fastapi import FastAPI, HTTPException
from src.rm.resource_manager import ResourceManager
from src.rms.models.models import InsertRequest, UpdateRequest, TxnRequest
import pymysql
import os
import requests
from src.rms.base.err_handle import handle_rm_result
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# port = 8001
app = FastAPI(title="Flight RM Service")

# -----------------------------
# RM 初始化（进程级单例）
# -----------------------------

conn = pymysql.connect(
    host="127.0.0.1",
    port=33061,
    user="root",
    password="1234",
    database="rm_db",
    autocommit=True,
    cursorclass=pymysql.cursors.DictCursor,
)

rm = ResourceManager(
    db_conn=conn,
    table="FLIGHTS",
    key_column="flightNum",
    page_size=2,
)

def enlist(req):
    requests.request(
        "POST",
        "http://127.0.0.1:9000/txn/enlist",
        json={"xid": req.xid, "rm": "http://127.0.0.1:8001"},
    )

# -----------------------------
# CRUD APIs
# -----------------------------

@app.get("/records/{key}")
def read_record(key: str, xid: int):
    res = rm.read(xid, key)
    record = handle_rm_result(res)
    return {"record": record}


@app.post("/records")
def insert_record(req: InsertRequest):
    res = rm.insert(req.xid, req.record)
    handle_rm_result(res)
    enlist(req)
    return {"ok": True}


@app.put("/records/{key}")
def update_record(key: str, req: UpdateRequest):
    res = rm.update(req.xid, key, req.updates)
    handle_rm_result(res)
    enlist(req)
    return {"ok": True}


@app.delete("/records/{key}")
def delete_record(key: str, xid: int):
    res = rm.delete(xid, key)
    handle_rm_result(res)
    enlist(TxnRequest(xid=xid))
    return {"ok": True}

# -----------------------------
# 2PC APIs
# -----------------------------

@app.post("/txn/prepare")
def prepare_txn(req: TxnRequest):
    res = rm.prepare(req.xid)
    if not res.ok:
        return {
            "ok": False,
            "error": res.err.name,
        }
    return {"ok": True}


@app.post("/txn/commit")
def commit_txn(req: TxnRequest):
    res = rm.commit(req.xid)
    handle_rm_result(res)
    return {"ok": True}


@app.post("/txn/abort")
def abort_txn(req: TxnRequest):
    res = rm.abort(req.xid)
    handle_rm_result(res)
    return {"ok": True}

# -----------------------------
# Ops APIs
# -----------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/shutdown")
def shutdown():
    # 简单实现：直接退出进程
    os._exit(0)
