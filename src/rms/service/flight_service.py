# src/rms/flight_rm_service.py
from fastapi import FastAPI, HTTPException
from src.rm.resource_manager import ResourceManager
from src.rms.models.models import InsertRequest, UpdateRequest, TxnRequest
import pymysql
import os
import requests

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
    record = rm.read(xid, key)
    if record is None:
        return {"record": None}
    return {"record": dict(record)}


@app.post("/records")
def insert_record(req: InsertRequest):
    try:
        rm.insert(req.xid, req.record)
        enlist(req)
        return {"ok": True}
    except KeyError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.put("/records/{key}")
def update_record(key: str, req: UpdateRequest):
    try:
        rm.update(req.xid, key, req.updates)
        enlist(req)
        return {"ok": True}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/records/{key}")
def delete_record(key: str, xid: int):
    rm.delete(xid, key)
    enlist(UpdateRequest(xid=xid, updates={}))
    return {"ok": True}

# -----------------------------
# 2PC APIs
# -----------------------------

@app.post("/txn/prepare")
def prepare_txn(req: TxnRequest):
    ok = rm.prepare(req.xid)
    return {"ok": ok}


@app.post("/txn/commit")
def commit_txn(req: TxnRequest):
    rm.commit(req.xid)
    return {"ok": True}


@app.post("/txn/abort")
def abort_txn(req: TxnRequest):
    rm.abort(req.xid)
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
