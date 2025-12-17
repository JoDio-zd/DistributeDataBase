"""
WC (Workflow Controller) Data Models

This module defines all Pydantic models for request/response validation.
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


# ========== Transaction Models ==========

class TransactionStatus(str, Enum):
    """Transaction status enumeration."""
    ACTIVE = "ACTIVE"
    PREPARING = "PREPARING"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"
    IN_DOUBT = "IN_DOUBT"


class TransactionResponse(BaseModel):
    """Response model for transaction operations."""
    xid: str = Field(..., description="Transaction ID")
    status: TransactionStatus = Field(..., description="Transaction status")
    message: Optional[str] = Field(None, description="Additional message")


# ========== Resource Models ==========

class FlightCreate(BaseModel):
    """Request model for creating a flight."""
    flightNum: str = Field(..., description="Flight number", min_length=1)
    price: int = Field(..., description="Price", ge=0)
    numSeats: int = Field(..., description="Total number of seats", ge=0)
    numAvail: int = Field(..., description="Available seats", ge=0)


class FlightUpdate(BaseModel):
    """Request model for updating a flight (partial update)."""
    price: Optional[int] = Field(None, description="Price", ge=0)
    numSeats: Optional[int] = Field(None, description="Total number of seats", ge=0)
    numAvail: Optional[int] = Field(None, description="Available seats", ge=0)


class FlightResponse(BaseModel):
    """Response model for flight data."""
    flightNum: str
    price: int
    numSeats: int
    numAvail: int


class HotelCreate(BaseModel):
    """Request model for creating a hotel."""
    location: str = Field(..., description="Hotel location", min_length=1)
    price: int = Field(..., description="Price", ge=0)
    numRooms: int = Field(..., description="Total number of rooms", ge=0)
    numAvail: int = Field(..., description="Available rooms", ge=0)


class HotelUpdate(BaseModel):
    """Request model for updating a hotel (partial update)."""
    price: Optional[int] = Field(None, description="Price", ge=0)
    numRooms: Optional[int] = Field(None, description="Total number of rooms", ge=0)
    numAvail: Optional[int] = Field(None, description="Available rooms", ge=0)


class HotelResponse(BaseModel):
    """Response model for hotel data."""
    location: str
    price: int
    numRooms: int
    numAvail: int


class CarCreate(BaseModel):
    """Request model for creating a car rental."""
    location: str = Field(..., description="Car rental location", min_length=1)
    price: int = Field(..., description="Price", ge=0)
    numCars: int = Field(..., description="Total number of cars", ge=0)
    numAvail: int = Field(..., description="Available cars", ge=0)


class CarUpdate(BaseModel):
    """Request model for updating a car rental (partial update)."""
    price: Optional[int] = Field(None, description="Price", ge=0)
    numCars: Optional[int] = Field(None, description="Total number of cars", ge=0)
    numAvail: Optional[int] = Field(None, description="Available cars", ge=0)


class CarResponse(BaseModel):
    """Response model for car rental data."""
    location: str
    price: int
    numCars: int
    numAvail: int


class CustomerCreate(BaseModel):
    """Request model for creating a customer."""
    custName: str = Field(..., description="Customer name", min_length=1)


class CustomerResponse(BaseModel):
    """Response model for customer data."""
    custName: str


# ========== Reservation Models ==========

class ReservationType(str, Enum):
    """Reservation type enumeration."""
    FLIGHT = "FLIGHT"
    HOTEL = "HOTEL"
    CAR = "CAR"


class ReserveRequest(BaseModel):
    """Request model for making a reservation."""
    custName: str = Field(..., description="Customer name", min_length=1)
    quantity: int = Field(1, description="Quantity to reserve", ge=1, le=10)


class ReservationCreate(BaseModel):
    """Request model for creating a reservation record (internal use by orchestrator)."""
    custName: str
    resvType: ReservationType
    resvKey: str


class ReservationResponse(BaseModel):
    """Response model for a single reservation."""
    resvType: ReservationType
    resvKey: str


class CustomerReservationsResponse(BaseModel):
    """Response model for customer reservations."""
    custName: str
    reservations: List[ReservationResponse]


class ReserveResponse(BaseModel):
    """Response model for reserve operation."""
    success: bool = True
    message: str = "Reservation created successfully"
    numAvail: Optional[int] = None


# ========== Admin Models ==========

class DieResponse(BaseModel):
    """Response model for die operation."""
    message: str = "WC service is shutting down"


class ReconnectResponse(BaseModel):
    """Response model for reconnect operation."""
    message: str
    tm_status: str
    rm_status: dict


# ========== Error Models ==========

class ErrorResponse(BaseModel):
    """Generic error response model."""
    error: str
    details: Optional[str] = None
    xid: Optional[str] = None
    transaction_aborted: bool = False
