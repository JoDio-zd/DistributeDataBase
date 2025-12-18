from src.rm.resource_manager import ResourceManager
import pymysql

def test_ww_conflict_2pc_simulated():
    conn = pymysql.connect(
        host="127.0.0.1",
        port=33061,
        user="root",
        password="1234",
        database="rm_db",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )

    rm = ResourceManager(
        db_conn=conn,
        table="FLIGHTS",
        key_column="flightNum",
        page_size=2,
    )

    # ======================
    # T1 / T2 并发执行阶段
    # ======================

    # T1 读 + 写（shadow）
    rm.read(1, "1234")
    rm.upsert(1, {
        "flightNum": "1222",
        "price": 300,
        "numSeats": 150,
        "numAvail": 120
    })

    # T2 读 + 写（shadow）
    rm.read(2, "1234")
    rm.upsert(2, {
        "flightNum": "1222",
        "price": 999,      # 写不同值，方便观察
        "numSeats": 150,
        "numAvail": 100
    })

    # ======================
    # 2PC 阶段（顺序模拟）
    # ======================

    # --- T1 先 prepare + commit ---
    print("T1 prepare:", rm.prepare(1))

    # --- T2 再 prepare（应失败：WW 冲突） ---
    print("T2 prepare:", rm.prepare(2))
    rm.commit(1)
    
    # 不需要 commit，prepare 失败即 abort
    # rm.abort(2)  # 如果您有 abort，可以显式调用

    conn.close()

if __name__ == "__main__":
    test_ww_conflict_2pc_simulated()
