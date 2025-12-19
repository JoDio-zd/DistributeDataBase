import src.wc.workflow_controller as wc

wc = wc.FlightWC()
xid = wc.start()
xid2 = wc.start()
try:
    flightnum = "1234"
    seatsAvailable = wc.queryFlight(xid, flightnum)
    print(f"Seats available for flight {flightnum}: {seatsAvailable}")
    wc.addFlight(xid, "1232", 10, 500)
except RuntimeError as e:
    print(e)
try:
    wc.addFlight(xid2, "1111", 20, 600)
except RuntimeError as e:
    print(e)
    
except RuntimeError as e:
    print(e)
try:
    wc.commit(xid2)
except RuntimeError as e:
    print(e)
try:
    wc.commit(xid)
except RuntimeError:
    print(e)