from fastapi import FastAPI, HTTPException
from typing import List

from src.rm.resource_manager import ResourceManager
from src.rm.flight.flight_schema import (
    FlightCreate,
    FlightResponse,
    FlightUpdate,
    FlightTableResponse,
)

# ✅ 初始化 ResourceManager
flight_rm = ResourceManager("FlightDB", "proto/flight.proto")

app = FastAPI(
    title="Flight RM Service",
    version="1.0.0",
    description="Resource Manager for Flight Table"
)

# ✅ Health Check
@app.get("/health")
def health():
    return {"status": "ok"}


# 📌 工具函数
def xid_required(xid: str):
    if not xid:
        raise HTTPException(status_code=400, detail="xid is required")


# ✅ 获取单条航班记录
@app.get("/flight/{xid}/{flightNum}",
         response_model=FlightResponse)
def get_flight(xid: str, flightNum: str):
    xid_required(xid)

    record = flight_rm.Get(flightNum)
    if record is None:
        raise HTTPException(status_code=404, detail="Flight not found")

    return FlightResponse(
        flightNum=record.flightNum,
        price=record.price,
        numSeats=record.numSeats,
        numAvail=record.numAvail,
    )


# ✅ 获取所有航班
@app.get("/flight/all",
         response_model=FlightTableResponse)
def get_all_flights():
    return FlightTableResponse(
        records={
            k: FlightResponse(
                flightNum=v.flightNum,
                price=v.price,
                numSeats=v.numSeats,
                numAvail=v.numAvail,
            )
            for k, v in flight_rm.Table.records.items()
        }
    )


# ✅ 添加航班
@app.post("/flight/{xid}", response_model=str)
def add_flight(xid: str, req: FlightCreate):
    xid_required(xid)

    # ✅ numAvail 初始化为 numSeats
    record = flight_rm.module.FlightRecord(
        flightNum=req.flightNum,
        price=req.price,
        numSeats=req.numSeats,
        numAvail=req.numSeats,
    )

    key = flight_rm.Add(record)  # 自增 id
    return f"Flight inserted with key={key}"


# ✅ 更新航班信息
@app.put("/flight/{xid}/{flightNum}")
def update_flight(xid: str, flightNum: str, req: FlightUpdate):
    xid_required(xid)

    cur = flight_rm.Table.records.get(flightNum)
    if cur is None:
        raise HTTPException(status_code=404, detail="Flight not found")

    new_record = flight_rm.module.FlightRecord(
        flightNum=cur.flightNum,
        price=req.price if req.price is not None else cur.price,
        numSeats=req.numSeats if req.numSeats is not None else cur.numSeats,
        numAvail=req.numAvail if req.numAvail is not None else cur.numAvail,
    )

    flight_rm.Table.records[flightNum].CopyFrom(new_record)

    return {"ok": True, "msg": "Updated"}


# ✅ 删除航班
@app.delete("/flight/{xid}/{flightNum}")
def delete_flight(xid: str, flightNum: str):
    xid_required(xid)

    ok = flight_rm.Delete(flightNum)
    if not ok:
        raise HTTPException(status_code=404, detail="Flight not found")

    return {"ok": True, "msg": "Deleted"}
