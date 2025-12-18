from src.rm.resource_manager import ResourceManager
import pymysql

def test_ww_conflict_insert_insert_simulated():
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

    key = "3456"

    # 0) 先确保目标 page 被加载进 committed_pool（避免 prepare 断言）
    rm.read(1, key)
    rm.read(2, key)

    # 1) T1/T2 都尝试 INSERT 同一个 key（写不同值方便观察）
    rm.insert(1, {
        "flightNum": key,
        "price": 300,
        "numSeats": 150,
        "numAvail": 120,
    })

    rm.insert(2, {
        "flightNum": key,
        "price": 999,
        "numSeats": 150,
        "numAvail": 100,
    })

    # 2) 2PC：先 prepare/commit T1
    ok1 = rm.prepare(1)
    print("T1 prepare:", ok1)
    if ok1:
        rm.commit(1)
        print("T1 committed.")
    else:
        rm.abort(1)
        print("T1 aborted (unexpected).")

    # 3) 再 prepare T2：预期失败（因为 T1 已提交插入）
    ok2 = rm.prepare(2)
    print("T2 prepare:", ok2)
    if ok2:
        # 走到这里说明并发控制有 bug（不应该让第二个 insert 通过）
        rm.commit(2)
        print("T2 committed (UNEXPECTED BUG).")
    else:
        rm.abort(2)
        print("T2 aborted (expected).")

    # 4) 验证最终 committed 值应是 T1 的版本
    final = rm.read(999, key)  # 用一个“读事务” xid
    print("Final record:", final)

    conn.close()


def test_ww_conflict_update_update_simulated():
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

    key = "7777"

    # 0) 确保基准记录存在（如果不存在就先插入一条作为“初始 committed”）
    rm.read(0, key)  # 先加载 page
    try:
        rm.insert(0, {
            "flightNum": key,
            "price": 100,
            "numSeats": 150,
            "numAvail": 150,
        })
        ok0 = rm.prepare(0)
        if ok0:
            rm.commit(0)
    except KeyError:
        pass  # 已存在就跳过

    # 1) T1/T2 都读取同一条记录（模拟并发读）
    r1 = rm.read(1, key)
    r2 = rm.read(2, key)
    print("T1 read:", r1)
    print("T2 read:", r2)

    # 2) 两个事务都更新同一个字段（制造 WW）
    rm.update(1, key, {"price": 200})
    rm.update(2, key, {"price": 999})

    # 3) 先提交 T1
    ok1 = rm.prepare(1)
    print("T1 prepare:", ok1)
    if ok1:
        rm.commit(1)
        print("T1 committed.")
    else:
        rm.abort(1)
        print("T1 aborted (unexpected).")

    # 4) 再提交 T2：预期 prepare 失败（version mismatch）
    ok2 = rm.prepare(2)
    print("T2 prepare:", ok2)
    if ok2:
        rm.commit(2)
        print("T2 committed (UNEXPECTED BUG).")
    else:
        rm.abort(2)
        print("T2 aborted (expected).")

    # 5) 验证最终 committed 应是 T1 的更新结果
    final = rm.read(999, key)
    print("Final record:", final)

    conn.close()

def test_ww_conflict_update_delete_simulated():
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

    key = "8888"

    # 0) 确保初始记录存在
    rm.read(0, key)
    try:
        rm.insert(0, {
            "flightNum": key,
            "price": 100,
            "numSeats": 150,
            "numAvail": 150,
        })
        if rm.prepare(0):
            rm.commit(0)
    except KeyError:
        pass

    # 1) T1 / T2 并发读
    rm.read(1, key)
    rm.read(2, key)

    # 2) T1 update，T2 delete
    rm.update(1, key, {"price": 200})
    rm.delete(2, key)

    # 3) 先提交 T1
    ok1 = rm.prepare(1)
    print("T1 prepare:", ok1)
    if ok1:
        rm.commit(1)
        print("T1 committed.")
    else:
        rm.abort(1)
        print("T1 aborted.")

    # 4) 再提交 T2：预期失败（version mismatch / already updated）
    ok2 = rm.prepare(2)
    print("T2 prepare:", ok2)
    if ok2:
        rm.commit(2)
        print("T2 committed (UNEXPECTED BUG).")
    else:
        rm.abort(2)
        print("T2 aborted (expected).")

    # 5) 验证最终状态：记录存在，price=200
    final = rm.read(999, key)
    print("Final record:", final)

    conn.close()


if __name__ == "__main__":
    test_ww_conflict_insert_insert_simulated()
    test_ww_conflict_update_update_simulated()
    test_ww_conflict_update_delete_simulated()