from src.rm.resource_manager import ResourceManager

def main():
    rm = ResourceManager("FlightDB", "proto/flight.proto")
    FlightRecord = rm.module.FlightRecord

    # id1 = rm.Add(FlightRecord(flightNum="CZ300", price=999, numSeats=120, numAvail=100))
    # print("New ID:", id1)

    print(rm.Get(2))

if __name__ == "__main__":
    main()