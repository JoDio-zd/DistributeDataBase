from src.wc.workflow_controller import WC
import pprint


def test_car_basic_flow():
    wc = WC()

    print("\n=== START CAR FLOW TEST ===")

    # 1. start txn
    xid = wc.start()
    print(f"[OK] txn started, xid={xid}")

    try:
        # 2. add customer
        cust = "Bob"
        wc.addCustomer(xid, cust)
        print("[OK] customer added")

        # 3. add car
        location = "SFO"
        wc.addCar(
            xid=xid,
            location=location,
            price=80,
            numCars=5,
        )
        print("[OK] car added")

        # 4. query car
        car = wc.queryCar(xid, location)
        assert car is not None, "car query failed"
        assert car["numAvail"] == 5
        print("[OK] car queried:")
        pprint.pprint(car)

        # 5. reserve car (1 car)
        wc.reserveCar(
            xid=xid,
            custName=cust,
            location=location,
        )
        print("[OK] car reserved (1 car)")

        # 6. query car again (still uncommitted view)
        car2 = wc.queryCar(xid, location)
        assert car2["numAvail"] == 4
        print("[OK] car availability updated in txn:")
        pprint.pprint(car2)

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

    car_final = wc.queryCar(xid2, location)
    assert car_final is not None
    assert car_final["numAvail"] == 4

    print("[OK] committed car state verified:")
    pprint.pprint(car_final)

    print("\n=== CAR FLOW TEST PASSED ===\n")


if __name__ == "__main__":
    test_car_basic_flow()
