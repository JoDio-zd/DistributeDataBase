import requests


class WC:
    def __init__(
        self,
        tm_url="http://127.0.0.1:9000",
        flight_rm_url="http://127.0.0.1:8001",
        hotel_rm_url="http://127.0.0.1:8002",
        car_rm_url="http://127.0.0.1:8003",
        customer_rm_url="http://127.0.0.1:8004",
    ):
        self.tm = tm_url.rstrip("/")
        self.flight_rm = flight_rm_url.rstrip("/")
        self.hotel_rm = hotel_rm_url.rstrip("/")
        self.car_rm = car_rm_url.rstrip("/")
        self.customer_rm = customer_rm_url.rstrip("/")

    # =========================================================
    # txn control
    # =========================================================

    def start(self) -> int:
        r = requests.post(f"{self.tm}/txn/start")
        r.raise_for_status()
        return r.json()["xid"]

    def commit(self, xid: int):
        r = requests.post(f"{self.tm}/txn/commit", json={"xid": xid})
        r.raise_for_status()
        if not r.json().get("ok", False):
            raise RuntimeError("commit failed")

    def abort(self, xid: int):
        requests.post(f"{self.tm}/txn/abort", params={"xid": xid})

    # =========================================================
    # Flight APIs
    # =========================================================

    def addFlight(self, xid: int, flightNum, price, numSeats):
        r = requests.post(
            f"{self.flight_rm}/records",
            json={
                "xid": xid,
                "record": {
                    "flightNum": flightNum,
                    "price": price,
                    "numSeats": numSeats,
                    "numAvail": numSeats,
                },
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def deleteFlight(self, xid: int, flightNum):
        r = requests.delete(
            f"{self.flight_rm}/records/{flightNum}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def queryFlight(self, xid: int, flightNum):
        r = requests.get(
            f"{self.flight_rm}/records/{flightNum}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            return None
        return r.json().get("record")

    def reserveFlight(self, xid: int, flightNum, seats=1):
        rec = self.queryFlight(xid, flightNum)
        if rec is None:
            raise RuntimeError("flight not found")
        if rec["numAvail"] < seats:
            raise RuntimeError("not enough seats")

        r = requests.put(
            f"{self.flight_rm}/records/{flightNum}",
            json={
                "xid": xid,
                "updates": {
                    "numAvail": rec["numAvail"] - seats
                },
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    # =========================================================
    # Hotel APIs
    # =========================================================

    def addHotel(self, xid: int, location, price, numRooms):
        r = requests.post(
            f"{self.hotel_rm}/records",
            json={
                "xid": xid,
                "record": {
                    "location": location,
                    "price": price,
                    "numRooms": numRooms,
                    "numAvail": numRooms,
                },
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def deleteHotel(self, xid: int, location):
        r = requests.delete(
            f"{self.hotel_rm}/records/{location}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def queryHotel(self, xid: int, location):
        r = requests.get(
            f"{self.hotel_rm}/records/{location}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            return None
        return r.json().get("record")

    def reserveHotel(self, xid: int, location, rooms=1):
        rec = self.queryHotel(xid, location)
        if rec is None:
            raise RuntimeError("hotel not found")
        if rec["numAvail"] < rooms:
            raise RuntimeError("not enough rooms")

        r = requests.put(
            f"{self.hotel_rm}/records/{location}",
            json={
                "xid": xid,
                "updates": {
                    "numAvail": rec["numAvail"] - rooms
                },
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    # =========================================================
    # Car APIs
    # =========================================================

    def addCar(self, xid: int, location, price, numCars):
        r = requests.post(
            f"{self.car_rm}/records",
            json={
                "xid": xid,
                "record": {
                    "location": location,
                    "price": price,
                    "numCars": numCars,
                    "numAvail": numCars,
                },
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def deleteCar(self, xid: int, location):
        r = requests.delete(
            f"{self.car_rm}/records/{location}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def queryCar(self, xid: int, location):
        r = requests.get(
            f"{self.car_rm}/records/{location}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            return None
        return r.json().get("record")

    def reserveCar(self, xid: int, location, cars=1):
        rec = self.queryCar(xid, location)
        if rec is None:
            raise RuntimeError("car location not found")
        if rec["numAvail"] < cars:
            raise RuntimeError("not enough cars")

        r = requests.put(
            f"{self.car_rm}/records/{location}",
            json={
                "xid": xid,
                "updates": {
                    "numAvail": rec["numAvail"] - cars
                },
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    # =========================================================
    # Customer APIs
    # =========================================================

    def addCustomer(self, xid: int, custId):
        r = requests.post(
            f"{self.customer_rm}/records",
            json={
                "xid": xid,
                "record": {
                    "custId": custId,
                    "reservations": [],
                },
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def deleteCustomer(self, xid: int, custId):
        r = requests.delete(
            f"{self.customer_rm}/records/{custId}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def queryCustomer(self, xid: int, custId):
        r = requests.get(
            f"{self.customer_rm}/records/{custId}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            return None
        return r.json().get("record")
