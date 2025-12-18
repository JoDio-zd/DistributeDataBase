import src.wc.workflow_controller as wc

wc = wc.FlightWC()
xid = wc.start()
xid2 = wc.start()
seatsAvailable = wc.queryFlight(xid, "0008")
wc.addFlight(xid, "9892", 10, 500)
wc.addFlight(xid2, "9892", 20, 600)
wc.commit(xid2)
wc.commit(xid)