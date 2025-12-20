from src.wc.workflow_controller import WC
import pprint


def test_flight_basic_flow():
    wc = WC()

    print("\n=== START FLIGHT FLOW TEST ===")

    # 1. start txn
    xid = wc.start()
    print(f"[OK] txn started, xid={xid}")

    try:
        # 2. add customer
        cust = "Alice"
        wc.addCustomer(xid, cust)
        print("[OK] customer added")

        # 3. add flight
        flight_num = "F100"
        wc.addFlight(
            xid=xid,
            flightNum=flight_num,
            price=500,
            numSeats=10,
        )
        print("[OK] flight added")

        # 4. query flight
        flight = wc.queryFlight(xid, flight_num)
        assert flight is not None, "flight query failed"
        assert flight["numAvail"] == 10
        print("[OK] flight queried:")
        pprint.pprint(flight)

        # 5. reserve flight (ALWAYS reserve exactly 1 seat)
        wc.reserveFlight(
            xid=xid,
            custName=cust,
            flightNum=flight_num,
        )
        print("[OK] flight reserved (1 seat)")

        # 6. query flight again (still uncommitted view)
        flight2 = wc.queryFlight(xid, flight_num)
        assert flight2["numAvail"] == 9
        print("[OK] flight availability updated in txn:")
        pprint.pprint(flight2)

        # 7. commit
        wc.commit(xid)
        print("[OK] txn committed")

    except Exception as e:
        print("[FAIL] error occurred, aborting txn")
        wc.abort(xid)
        raise

    # 8. verify committed state with a new txn
    xid2 = wc.start()
    print(f"\n[VERIFY] new txn xid={xid2}")

    flight_final = wc.queryFlight(xid2, flight_num)
    assert flight_final is not None
    assert flight_final["numAvail"] == 9

    print("[OK] committed flight state verified:")
    pprint.pprint(flight_final)

    print("\n=== FLIGHT FLOW TEST PASSED ===\n")


if __name__ == "__main__":
    test_flight_basic_flow()
