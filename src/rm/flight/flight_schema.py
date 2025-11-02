from pydantic import BaseModel, Field
from typing import Optional, Dict


# ----------------------------------------
# Flight Record - Base Model
# 对应 proto: FlightRecord
# ----------------------------------------
class FlightBase(BaseModel):
    flightNum: str = Field(..., description="航班编号")
    price: float = Field(..., ge=0, description="票价")
    numSeats: int = Field(..., ge=0, description="总座位数")
    numAvail: int = Field(..., ge=0, description="可用座位数")


# ----------------------------------------
# ✅ Create 请求模型
# 不允许手动指定 numAvail
# ----------------------------------------
class FlightCreate(BaseModel):
    flightNum: str = Field(..., description="航班编号")
    price: float = Field(..., ge=0, description="票价")
    numSeats: int = Field(..., ge=0, description="总座位数")


# ----------------------------------------
# ✅ Update 请求模型
# 都可选（PATCH 语义）
# ----------------------------------------
class FlightUpdate(BaseModel):
    price: Optional[float] = Field(None, ge=0)
    numSeats: Optional[int] = Field(None, ge=0)
    numAvail: Optional[int] = Field(None, ge=0)


# ----------------------------------------
# ✅ Read / Response 模型
# 完整返回数据库中的记录
# ----------------------------------------
class FlightResponse(FlightBase):
    flightNum: str = Field(..., description="航班编号")
    price: float = Field(..., ge=0, description="票价")
    numSeats: int = Field(..., ge=0, description="总座位数")
    numAvail: int = Field(..., ge=0, description="可用座位数")

# ----------------------------------------
# ✅ Flight Table（响应用）
# 对应 proto: FlightTable { map<string, FlightRecord> records }
# ----------------------------------------
class FlightTableResponse(BaseModel):
    records: Dict[str, FlightResponse]
