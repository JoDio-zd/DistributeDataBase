# src/rms/models.py
from pydantic import BaseModel
from typing import Dict, Any


class InsertRequest(BaseModel):
    xid: int
    record: Dict[str, Any]


class UpdateRequest(BaseModel):
    xid: int
    updates: Dict[str, Any]


class TxnRequest(BaseModel):
    xid: int
