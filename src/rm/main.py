from src.rm.resource_manager import ResourceManager

if __name__ == "__main__":
    flight_db = ResourceManager("FlightDB", "proto/flight.proto")
    customer_db = ResourceManager("CustomerDB", "proto/customer.proto")
    car_db = ResourceManager("CarDB", "proto/car.proto")
    hotel_db = ResourceManager("HotelDB", "proto/hotel.proto")
    reservation_db = ResourceManager("ReservationDB", "proto/reservation.proto")

    flight_db.Info()
    customer_db.Info()
    car_db.Info()
    hotel_db.Info()
    reservation_db.Info()

    FlightRecord = flight_db.module.FlightRecord
    record = FlightRecord(
        flightNum="CZ300",
        price=999.0,
        numSeats=120,
        numAvail=100
    )
    flight_db.Add(record)
