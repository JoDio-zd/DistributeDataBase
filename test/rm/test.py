from src.rm.resource_manager import ResourceManager
import pymysql

def test_rm_init():
    conn = pymysql.connect(
        host="127.0.0.1",
        port=33061,
        user="root",
        password="1234",
        database="rm_db",
        autocommit=True,   # 非常重要
        cursorclass=pymysql.cursors.DictCursor,
    )
    rm = ResourceManager(
        db_conn=conn,
        table="FLIGHTS",
        key_column="flightNum",
        page_size=2,
    )
    res = rm.read(1, "1")
    res = rm.read(1, "2")
    res = rm.read(1, "8")
    res = rm.read(1, "7")
    res = rm.read(1, "22hs")
    res = rm.upsert(1, {
        "flightNum": "1234",
        "price": 300,
        "numSeats": 150,
        "numAvail": 120
    })
    res = rm.read(2, "1234")
    if res is None:
        print("Record not found")
    res = rm.read(1, "1234")
    if res is None:
        print("Record not found")
    res = rm.delete(1, "1234")
    res = rm.commit(1)

if __name__ == "__main__":
    test_rm_init()