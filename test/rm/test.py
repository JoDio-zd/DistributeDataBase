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
    print("finding record 1")
    res = rm.read(1, "1")
    if res is None:
        print("Record not found.")
    print("finding record 2")
    res = rm.read(1, "2")
    if res is None:
        print("Record not found.")
    print("finding record 8")
    res = rm.read(1, "8")
    if res is None:
        print("Record not found.")
    print("finding record 7")
    res = rm.read(1, "7")
    if res is None:
        print("Record not found.")
    print("finding record 1020")
    res = rm.read(1, "22hs")
    if res is None:
        print("Record not found.")


if __name__ == "__main__":
    test_rm_init()