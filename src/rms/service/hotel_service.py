# src/rms/hotel_rm_service.py
from fastapi import FastAPI
from src.rm.resource_manager import ResourceManager
from src.rm.impl.page_io.mysql_page_io import MySQLPageIO
from src.rm.impl.page_index.order_string_page_index import OrderedStringPageIndex
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

# port = 8002
app = FastAPI(title="Hotel RM Service")

# -----------------------------
# RM 初始化（进程级单例）
# -----------------------------

conn = pymysql.connect(
    host="127.0.0.1",
    port=33062,
    user="root",
    password="1234",
    database="rm_db",
    autocommit=True,
    cursorclass=pymysql.cursors.DictCursor,
)

page_size = 2
key_width = 10

page_index = OrderedStringPageIndex(
    page_size=page_size,
    key_width=key_width,
)

page_io = MySQLPageIO(
    conn=conn,
    table="HOTELS",
    key_column="location",
    page_index=page_index,
)

rm = ResourceManager(
    page_index=page_index,
    page_io=page_io,
    table="HOTELS",
    key_column="location",
    key_width=key_width,
)

def enlist(req):
    requests.request(
        "POST",
        "http://127.0.0.1:9001/txn/enlist",
        json={"xid": req.xid, "rm": "http://127.0.0.1:8002"},
        timeout=3,
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
    os._exit(0)
