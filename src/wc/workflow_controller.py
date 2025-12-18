import requests

class FlightWC:
    def __init__(self, tm_url="http://127.0.0.1:9000",
                       flight_rm_url="http://127.0.0.1:8001"):
        self.tm = tm_url.rstrip("/")
        self.rm = flight_rm_url.rstrip("/")

    # -------------------------
    # txn control
    # -------------------------

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

    # -------------------------
    # business APIs (xid REQUIRED)
    # -------------------------

    def addFlight(self, xid: int, flightNum, price, numSeats):
        numAvail = numSeats
        r = requests.post(
            f"{self.rm}/records",
            json={
                "xid": xid,
                "record": {
                    "flightNum": flightNum,
                    "price": price,
                    "numSeats": numSeats,
                    "numAvail": numAvail,
                },
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def deleteFlight(self, xid: int, flightNum):
        r = requests.delete(
            f"{self.rm}/records/{flightNum}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

    def queryFlight(self, xid: int, flightNum):
        r = requests.get(
            f"{self.rm}/records/{flightNum}",
            params={"xid": xid},
        )
        if r.status_code != 200:
            return None
        return r.json().get("record")

    def reserveFlight(self, xid: int, flightNum, seats=1):
        # read
        r = requests.get(
            f"{self.rm}/records/{flightNum}",
            params={"xid": xid},
        )
        if r.status_code != 200 or r.json()["record"] is None:
            raise RuntimeError("flight not found")

        rec = r.json()["record"]
        if rec["numAvail"] < seats:
            raise RuntimeError("not enough seats")

        # write
        r = requests.put(
            f"{self.rm}/records/{flightNum}",
            json={
                "xid": xid,
                "updates": {
                    "numAvail": rec["numAvail"] - seats
                },
            },
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)
