from fastapi import FastAPI
from src.rm.resource_manager import ResourceManager
from src.rms.models.models import InsertRequest, UpdateRequest, TxnRequest
from src.rm.impl.mysql_page_io import MySQLPageIO
from src.rm.impl.order_string_page_index import OrderedStringPageIndex
import pymysql
import os
import requests
from src.rms.base.err_handle import handle_rm_result
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="Reservation RM Service")

# -----------------------------
# RM 初始化（进程级单例）
# -----------------------------

conn = pymysql.connect(
    host="127.0.0.1",
    port=33064,
    user="root",
    password="1234",
    database="rm_db",
    autocommit=True,
    cursorclass=pymysql.cursors.DictCursor,
)

page_size = 16
key_width = 26

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
    table="RESERVATIONS",
    key_column="custName|resvType|resvKey",
    key_width=key_width,
)

def enlist(req: TxnRequest):
    requests.request(
        "POST",
        "http://127.0.0.1:9000/txn/enlist",
        json={"xid": req.xid, "rm": "http://127.0.0.1:8005"},
        timeout=3,
    )

# -----------------------------
# Key Encoding / Decoding
# -----------------------------

# custName|resvType|resvKey
# Len(10)|Len(6)|Len(10) = 26
def encode_key(cust_name: str, resv_type: str, resv_key: str) -> str:
    cust_name = cust_name.zfill(10)[:10]
    resv_type = resv_type.ljust(6)[:6]
    resv_key = resv_key.zfill(10)[:10]
    return f"{cust_name}|{resv_type}|{resv_key}"

# -----------------------------
# CRUD APIs
# -----------------------------

@app.get("/records")
def read_record(
    custName: str,
    resvType: str,
    resvKey: str,
    xid: int,
):
    key = encode_key(custName, resvType, resvKey)
    res = rm.read(xid, key)
    record = handle_rm_result(res)
    return {"record": record}


@app.post("/records")
def insert_record(req: InsertRequest):
    """
    req.record should contain:
    {
        "custName": "...",
        "resvType": "FLIGHT" | "HOTEL" | "CAR",
        "resvKey": "...",
        ...
    }
    """
    record = req.record
    key = encode_key(
        record["custName"],
        record["resvType"],
        record["resvKey"],
    )

    # RM 层仍然只认一个 key
    record["__rm_key__"] = key

    res = rm.insert(req.xid, record)
    handle_rm_result(res)
    enlist(req)
    return {"ok": True}


@app.put("/records")
def update_record(
    custName: str,
    resvType: str,
    resvKey: str,
    req: UpdateRequest,
):
    key = encode_key(custName, resvType, resvKey)
    res = rm.update(req.xid, key, req.updates)
    handle_rm_result(res)
    enlist(req)
    return {"ok": True}


@app.delete("/records")
def delete_record(
    custName: str,
    resvType: str,
    resvKey: str,
    xid: int,
):
    key = encode_key(custName, resvType, resvKey)
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
