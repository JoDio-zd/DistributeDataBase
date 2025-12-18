from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Set, Dict
import threading
import requests
import os

# port = 9000
app = FastAPI(title="Transaction Manager Service")

# =========================================================
# Data model
# =========================================================

class Txn:
    def __init__(self):
        self.state = "ACTIVE"          # ACTIVE | COMMITTED | ABORTED
        self.rms: Set[str] = set()


transactions: Dict[int, Txn] = {}
_next_xid = 1
_lock = threading.Lock()   # protect xid + transactions


# =========================================================
# Request models
# =========================================================

class EnlistRequest(BaseModel):
    xid: int
    rm: str   # RM service base URL, e.g. http://127.0.0.1:8001


class TxnRequest(BaseModel):
    xid: int


# =========================================================
# APIs for WC (client)
# =========================================================

@app.post("/txn/start")
def start_txn():
    global _next_xid
    with _lock:
        xid = _next_xid
        _next_xid += 1
        transactions[xid] = Txn()
    return {"xid": xid}


@app.post("/txn/commit")
def commit_txn(req: TxnRequest):
    xid = req.xid
    txn = transactions.get(xid)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if txn.state != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail=f"Transaction already {txn.state}"
        )

    # ---------- Phase 1: prepare ----------
    for rm in txn.rms:
        try:
            resp = requests.post(f"{rm}/txn/prepare", json={"xid": xid}, timeout=3)
            ok = resp.json().get("ok", False)
            if not ok:
                raise Exception("prepare failed")
        except Exception:
            # prepare failed → abort all
            for r in txn.rms:
                _safe_abort(r, xid)
            txn.state = "ABORTED"
            return {"ok": False}

    # ---------- Phase 2: commit ----------
    for rm in txn.rms:
        _safe_commit(rm, xid)

    txn.state = "COMMITTED"
    return {"ok": True}


@app.post("/txn/abort")
def abort_txn(req: TxnRequest):
    xid = req.xid
    txn = transactions.get(xid)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if txn.state == "ABORTED":
        return {"ok": True}

    for rm in txn.rms:
        _safe_abort(rm, xid)

    txn.state = "ABORTED"
    return {"ok": True}


# =========================================================
# API for RM Service (enlist)
# =========================================================

@app.post("/txn/enlist")
def enlist(req: EnlistRequest):
    xid = req.xid
    txn = transactions.get(xid)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if txn.state != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail=f"Transaction already {txn.state}"
        )

    txn.rms.add(req.rm)   # set 保证幂等
    return {"ok": True}


# =========================================================
# Ops
# =========================================================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/die")
def die():
    os._exit(0)


# =========================================================
# Helpers (never throw)
# =========================================================

def _safe_commit(rm: str, xid: int):
    try:
        requests.post(f"{rm}/txn/commit", json={"xid": xid}, timeout=3)
    except Exception:
        pass   # 2PC 语义下：commit 阶段不回滚


def _safe_abort(rm: str, xid: int):
    try:
        requests.post(f"{rm}/txn/abort", json={"xid": xid}, timeout=3)
    except Exception:
        pass
