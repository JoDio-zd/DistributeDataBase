from src.wc.workflow_controller import WC
import pprint


def test_hotel_basic_flow_with_existing_customer():
    wc = WC()

    print("\n=== START HOTEL FLOW TEST (EXISTING CUSTOMER) ===")

    cust = "Alice"          # ⚠️ 复用已有用户
    location = "SHANGHAI"

    # 1. start txn
    xid = wc.start()
    print(f"[OK] txn started, xid={xid}")

    try:
        # 2. query customer (must exist)
        customer = wc.queryCustomer(xid, cust)
        assert customer is not None, "customer should already exist"
        print("[OK] existing customer verified")

        # 3. add hotel
        wc.addHotel(
            xid=xid,
            location=location,
            price=800,
            numRooms=5,
        )
        print("[OK] hotel added")

        # 4. query hotel
        hotel = wc.queryHotel(xid, location)
        assert hotel is not None, "hotel query failed"
        assert hotel["numAvail"] == 5
        print("[OK] hotel queried:")
        pprint.pprint(hotel)

        # 5. reserve hotel (ALWAYS reserve exactly 1 room)
        wc.reserveHotel(
            xid=xid,
            custName=cust,
            location=location,
        )
        print("[OK] hotel reserved (1 room)")

        # 6. query hotel again (uncommitted view)
        hotel2 = wc.queryHotel(xid, location)
        assert hotel2["numAvail"] == 4
        print("[OK] hotel availability updated in txn:")
        pprint.pprint(hotel2)

        # 7. commit
        wc.commit(xid)
        print("[OK] txn committed")

    except Exception as e:
        print("[FAIL] error occurred, aborting txn")
        wc.abort(xid)
        raise

    # 8. verify committed state in new txn
    xid2 = wc.start()
    print(f"\n[VERIFY] new txn xid={xid2}")

    hotel_final = wc.queryHotel(xid2, location)
    assert hotel_final is not None
    assert hotel_final["numAvail"] == 4

    print("[OK] committed hotel state verified:")
    pprint.pprint(hotel_final)

    print("\n=== HOTEL FLOW TEST PASSED ===\n")


if __name__ == "__main__":
    test_hotel_basic_flow_with_existing_customer()
