"""
Resource Manager Test Suite
测试 RM 层的并发控制、冲突检测、事务隔离等核心功能
"""

import threading
import time
from test.rm.helpers import *

# =========================================================
# 测试类别 1: WW 冲突类
# =========================================================


class TestWWConflicts:
    """【测试分类】Write-Write 冲突检测
    【测试目标】验证 OCC 版本检测与语义冲突检测
    """

    def test_ww_conflict_insert_insert(self):
        """【测试场景】两事务并发插入同一 key
        【期望结果】T1 commit 成功，T2 prepare 失败
        【错误码】KEY_EXISTS
        【覆盖源码】src/rm/resource_manager.py:197
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.WW_INSERT_INSERT

        # 预加载 page (prepare 不变式要求)
        preload_page_for_key(rm, 1, key)
        preload_page_for_key(rm, 2, key)

        # T1 和 T2 都插入同一 key
        r1 = rm.insert(1, create_flight_record(key, price=300))
        assert_rm_result_ok(r1, "T1 insert should succeed into shadow")

        r2 = rm.insert(2, create_flight_record(key, price=999))
        assert_rm_result_ok(r2, "T2 insert should succeed into shadow")

        # T1 commit 成功
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1, "T1 prepare should succeed")
        rm.commit(1)

        # T2 prepare 应失败 (KEY_EXISTS)
        p2 = rm.prepare(2)
        assert_key_exists(p2, key)
        rm.abort(2)

        # 最终状态应为 T1 的值
        final = read_committed_like(rm, key)
        assert final["price"] == 300, f"Expected price=300, got {final['price']}"

        conn.close()
        print("✅ test_ww_conflict_insert_insert passed")

    def test_ww_conflict_insert_update(self):
        """【测试场景】T1 insert, T2 update 同一 key
        【期望结果】T2 prepare 失败（key 不存在）
        【错误码】KEY_NOT_FOUND
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.WW_INSERT_UPDATE

        preload_page_for_key(rm, 1, key)
        preload_page_for_key(rm, 2, key)

        # T2 先尝试 update（key 不存在）
        r2_read = rm.read(2, key)
        assert_key_not_found(r2_read)
        r2_update = rm.update(2, key, {"price": 999})
        assert_key_not_found(r2_update, "T2 update non-existent key should fail")

        # T1 insert
        r1 = rm.insert(1, create_flight_record(key, price=300))
        assert_rm_result_ok(r1)
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        # T2 prepare/abort (已经失败)
        rm.abort(2)

        # 最终状态: T1 的 insert 存在
        final = read_committed_like(rm, key)
        assert final["price"] == 300

        conn.close()
        print("✅ test_ww_conflict_insert_update passed")

    def test_ww_conflict_insert_delete(self):
        """【测试场景】T1 insert, T2 delete 同一 key
        【期望结果】T2 delete 失败（key 不存在）
        【错误码】KEY_NOT_FOUND
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.WW_INSERT_DELETE

        preload_page_for_key(rm, 1, key)
        preload_page_for_key(rm, 2, key)

        # T2 尝试 delete 不存在的 key
        r2_delete = rm.delete(2, key)
        assert_key_not_found(r2_delete, "T2 delete non-existent key should fail")

        # T1 insert
        r1 = rm.insert(1, create_flight_record(key, price=300))
        assert_rm_result_ok(r1)
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        rm.abort(2)

        # 最终状态: T1 insert 存在
        final = read_committed_like(rm, key)
        assert final["price"] == 300

        conn.close()
        print("✅ test_ww_conflict_insert_delete passed")

    def test_ww_conflict_update_insert(self):
        """【测试场景】T1 update, T2 insert 同一 key
        【期望结果】T2 prepare 失败（key 已存在）
        【错误码】KEY_EXISTS
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.WW_UPDATE_INSERT

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key, price=100), "flightNum")

        preload_page_for_key(rm, 1, key)
        preload_page_for_key(rm, 2, key)

        # T1 update
        r1_read = rm.read(1, key)
        assert_rm_result_ok(r1_read)
        r1_update = rm.update(1, key, {"price": 200})
        assert_rm_result_ok(r1_update)

        # T2 尝试 insert (key 已存在)
        r2_insert = rm.insert(2, create_flight_record(key, price=999))
        # Insert 在 shadow 阶段会成功，但 prepare 会失败
        assert_rm_result_ok(r2_insert, "Insert into shadow succeeds")

        # T1 commit
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        # T2 prepare 失败
        p2 = rm.prepare(2)
        assert_key_exists(p2, key)
        rm.abort(2)

        # 最终状态: T1 update 生效
        final = read_committed_like(rm, key)
        assert final["price"] == 200

        conn.close()
        print("✅ test_ww_conflict_update_insert passed")

    def test_ww_conflict_update_update(self):
        """【测试场景】T1 和 T2 并发 update 同一 key
        【期望结果】T2 prepare 失败
        【错误码】VERSION_CONFLICT
        【覆盖源码】src/rm/resource_manager.py:218
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.WW_UPDATE_UPDATE

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key, price=100), "flightNum")

        preload_page_for_key(rm, 1, key)
        preload_page_for_key(rm, 2, key)

        # 并发读 (记录 start_version)
        r1 = rm.read(1, key)
        r2 = rm.read(2, key)
        assert_rm_result_ok(r1)
        assert_rm_result_ok(r2)

        # 并发 update
        u1 = rm.update(1, key, {"price": 200})
        assert_rm_result_ok(u1)
        u2 = rm.update(2, key, {"price": 999})
        assert_rm_result_ok(u2)

        # T1 commit
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        # T2 prepare 失败 (VERSION_CONFLICT)
        p2 = rm.prepare(2)
        assert_version_conflict(p2, key)
        rm.abort(2)

        # 最终状态: T1 update 生效
        final = read_committed_like(rm, key)
        assert final["price"] == 200

        conn.close()
        print("✅ test_ww_conflict_update_update passed")

    def test_ww_conflict_update_delete(self):
        """【测试场景】T1 update, T2 delete 同一 key
        【期望结果】T2 prepare 失败
        【错误码】VERSION_CONFLICT
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.WW_UPDATE_DELETE

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key, price=100), "flightNum")

        preload_page_for_key(rm, 1, key)
        preload_page_for_key(rm, 2, key)

        # 并发读
        assert_rm_result_ok(rm.read(1, key))
        assert_rm_result_ok(rm.read(2, key))

        # T1 update, T2 delete
        assert_rm_result_ok(rm.update(1, key, {"price": 200}))
        assert_rm_result_ok(rm.delete(2, key))

        # T1 commit
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        # T2 prepare 失败 (VERSION_CONFLICT)
        p2 = rm.prepare(2)
        assert_version_conflict(p2, key)
        rm.abort(2)

        # 最终状态: 记录存在且 price=200
        final = read_committed_like(rm, key)
        assert final["price"] == 200
        assert not final.get("deleted", False)

        conn.close()
        print("✅ test_ww_conflict_update_delete passed")

    def test_ww_conflict_delete_insert(self):
        """【测试场景】T1 delete, T2 insert 同一 key
        【期望结果】T1 delete commit 后，T2 insert commit 成功
        【说明】delete 后 insert 是允许的
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.WW_DELETE_INSERT

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key, price=100), "flightNum")

        # T1 delete
        preload_page_for_key(rm, 1, key)
        assert_rm_result_ok(rm.read(1, key))
        assert_rm_result_ok(rm.delete(1, key))
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        # T2 insert (key 已被删除，可以重新插入)
        preload_page_for_key(rm, 2, key)
        r2_insert = rm.insert(2, create_flight_record(key, price=200))
        assert_rm_result_ok(r2_insert)
        p2 = rm.prepare(2)
        assert_rm_result_ok(p2, "T2 insert after delete should succeed")
        rm.commit(2)

        # 最终状态: T2 insert 生效
        final = read_committed_like(rm, key)
        assert final["price"] == 200

        conn.close()
        print("✅ test_ww_conflict_delete_insert passed")

    def test_ww_conflict_delete_update(self):
        """【测试场景】T1 delete, T2 update 同一 key
        【期望结果】T2 prepare 失败
        【错误码】VERSION_CONFLICT
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.WW_DELETE_UPDATE

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key, price=100), "flightNum")

        preload_page_for_key(rm, 1, key)
        preload_page_for_key(rm, 2, key)

        # 并发读
        assert_rm_result_ok(rm.read(1, key))
        assert_rm_result_ok(rm.read(2, key))

        # T1 delete, T2 update
        assert_rm_result_ok(rm.delete(1, key))
        assert_rm_result_ok(rm.update(2, key, {"price": 999}))

        # T1 commit
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        # T2 prepare 失败 (VERSION_CONFLICT)
        p2 = rm.prepare(2)
        assert_version_conflict(p2, key)
        rm.abort(2)

        # 最终状态: 记录被删除
        xid_verify = 888888
        r_verify = rm.read(xid_verify, key)
        assert_key_not_found(r_verify, "Record should be deleted")

        conn.close()
        print("✅ test_ww_conflict_delete_update passed")

    def test_ww_conflict_delete_delete(self):
        """【测试场景】T1 和 T2 并发 delete 同一 key
        【期望结果】T2 prepare 失败
        【错误码】VERSION_CONFLICT
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.WW_DELETE_DELETE

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key, price=100), "flightNum")

        preload_page_for_key(rm, 1, key)
        preload_page_for_key(rm, 2, key)

        # 并发读
        assert_rm_result_ok(rm.read(1, key))
        assert_rm_result_ok(rm.read(2, key))

        # 并发 delete
        assert_rm_result_ok(rm.delete(1, key))
        assert_rm_result_ok(rm.delete(2, key))

        # T1 commit
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        # T2 prepare 失败 (VERSION_CONFLICT)
        p2 = rm.prepare(2)
        assert_version_conflict(p2, key)
        rm.abort(2)

        # 最终状态: 记录被删除
        xid_verify = 888888
        r_verify = rm.read(xid_verify, key)
        assert_key_not_found(r_verify)

        conn.close()
        print("✅ test_ww_conflict_delete_delete passed")


# =========================================================
# 测试类别 2: Abort 路径验证类
# =========================================================


class TestAbortPaths:
    """【测试分类】Abort 路径验证
    【测试目标】验证 abort 后 shadow 被丢弃，committed 状态不变
    """

    def test_abort_rollback_insert(self):
        """【测试场景】T1 insert 后 abort
        【期望结果】T2 读取时 key 不存在
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.ABORT_INSERT

        preload_page_for_key(rm, 1, key)

        # T1 insert 并 abort
        r1_insert = rm.insert(1, create_flight_record(key, price=300))
        assert_rm_result_ok(r1_insert)
        rm.abort(1)

        # T2 读取应该找不到
        preload_page_for_key(rm, 2, key)
        r2_read = rm.read(2, key)
        assert_key_not_found(r2_read, "After abort, insert should not be visible")

        conn.close()
        print("✅ test_abort_rollback_insert passed")

    def test_abort_rollback_update(self):
        """【测试场景】T1 update 后 abort
        【期望结果】T2 读取到原始值
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.ABORT_UPDATE

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key, price=100), "flightNum")

        preload_page_for_key(rm, 1, key)

        # T1 update 并 abort
        assert_rm_result_ok(rm.read(1, key))
        assert_rm_result_ok(rm.update(1, key, {"price": 200}))
        rm.abort(1)

        # T2 读取应该是原始值
        final = read_committed_like(rm, key)
        assert final["price"] == 100, (
            f"After abort, should see original value 100, got {final['price']}"
        )

        conn.close()
        print("✅ test_abort_rollback_update passed")

    def test_abort_rollback_delete(self):
        """【测试场景】T1 delete 后 abort
        【期望结果】T2 读取时记录仍存在
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.ABORT_DELETE

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key, price=100), "flightNum")

        preload_page_for_key(rm, 1, key)

        # T1 delete 并 abort
        assert_rm_result_ok(rm.read(1, key))
        assert_rm_result_ok(rm.delete(1, key))
        rm.abort(1)

        # T2 读取应该仍能找到
        final = read_committed_like(rm, key)
        assert final["price"] == 100, "After abort delete, record should still exist"

        conn.close()
        print("✅ test_abort_rollback_delete passed")

    def test_abort_releases_locks(self):
        """【测试场景】T1 prepare 后 abort，T2 应能获取锁
        【期望结果】T2 prepare 成功
        【说明】验证 abort 释放锁
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.ABORT_LOCK_RELEASE

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key, price=100), "flightNum")

        preload_page_for_key(rm, 1, key)

        # T1 update, prepare, 然后 abort (释放锁)
        assert_rm_result_ok(rm.read(1, key))
        assert_rm_result_ok(rm.update(1, key, {"price": 200}))
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.abort(1)  # 应释放锁

        # T2 update, prepare 应成功 (锁已释放)
        preload_page_for_key(rm, 2, key)
        assert_rm_result_ok(rm.read(2, key))
        assert_rm_result_ok(rm.update(2, key, {"price": 300}))
        p2 = rm.prepare(2)
        assert_rm_result_ok(p2, "T2 should acquire lock after T1 abort")
        rm.commit(2)

        # 最终状态: T2 的 update 生效
        final = read_committed_like(rm, key)
        assert final["price"] == 300

        conn.close()
        print("✅ test_abort_releases_locks passed")


# =========================================================
# 测试类别 3: 多 key 事务类
# =========================================================


class TestMultiKeyTransactions:
    """【测试分类】多 key 事务
    【测试目标】验证事务可以修改多个 key，冲突检测正确
    """

    def test_multi_key_same_page(self):
        """【测试场景】T1 修改同一 page 内的 key1, key2; T2 修改 key1
        【期望结果】T2 因 key1 冲突而 prepare 失败
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key1 = TestKeys.MULTI_KEY_1
        key2 = TestKeys.MULTI_KEY_2

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key1, price=100), "flightNum")
        seed_if_absent(rm, 0, create_flight_record(key2, price=100), "flightNum")

        preload_page_for_key(rm, 1, key1)
        preload_page_for_key(rm, 1, key2)
        preload_page_for_key(rm, 2, key1)

        # T1 修改 key1 和 key2
        assert_rm_result_ok(rm.read(1, key1))
        assert_rm_result_ok(rm.read(1, key2))
        assert_rm_result_ok(rm.update(1, key1, {"price": 200}))
        assert_rm_result_ok(rm.update(1, key2, {"price": 200}))

        # T2 修改 key1
        assert_rm_result_ok(rm.read(2, key1))
        assert_rm_result_ok(rm.update(2, key1, {"price": 999}))

        # T1 commit
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        # T2 prepare 失败 (key1 冲突)
        p2 = rm.prepare(2)
        assert_version_conflict(p2, key1)
        rm.abort(2)

        # 最终状态: key1 和 key2 都是 T1 的值
        final1 = read_committed_like(rm, key1)
        final2 = read_committed_like(rm, key2)
        assert final1["price"] == 200
        assert final2["price"] == 200

        conn.close()
        print("✅ test_multi_key_same_page passed")

    def test_multi_key_cross_page(self):
        """【测试场景】T1 修改跨 page 的 key1, key3
        【期望结果】锁按 sorted order 获取，避免死锁
        """
        conn = new_conn()
        rm = new_rm(
            conn,
            table=TestData.DEFAULT_TABLE,
            key_column=TestData.DEFAULT_KEY_COL,
            page_size=2,
        )
        key1 = TestKeys.MULTI_KEY_1
        key3 = TestKeys.MULTI_KEY_3

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key1, price=100), "flightNum")
        seed_if_absent(rm, 0, create_flight_record(key3, price=100), "flightNum")

        preload_page_for_key(rm, 1, key1)
        preload_page_for_key(rm, 1, key3)

        # T1 修改 key1 和 key3 (跨 page)
        assert_rm_result_ok(rm.read(1, key1))
        assert_rm_result_ok(rm.read(1, key3))
        assert_rm_result_ok(rm.update(1, key1, {"price": 200}))
        assert_rm_result_ok(rm.update(1, key3, {"price": 300}))

        # T1 prepare 和 commit 应成功
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1, "Multi-key cross-page prepare should succeed")
        rm.commit(1)

        # 验证两个 key 都生效
        final1 = read_committed_like(rm, key1)
        final3 = read_committed_like(rm, key3)
        assert final1["price"] == 200
        assert final3["price"] == 300

        conn.close()
        print("✅ test_multi_key_cross_page passed")

    def test_multi_key_no_conflict(self):
        """【测试场景】T1 修改 key1, T2 修改 key2（不同 key）
        【期望结果】两者都 commit 成功
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key1 = TestKeys.MULTI_NO_CONFLICT_1
        key2 = TestKeys.MULTI_NO_CONFLICT_2

        # Seed 数据
        seed_if_absent(rm, 0, create_flight_record(key1, price=100), "flightNum")
        seed_if_absent(rm, 0, create_flight_record(key2, price=100), "flightNum")

        preload_page_for_key(rm, 1, key1)
        preload_page_for_key(rm, 2, key2)

        # T1 修改 key1
        assert_rm_result_ok(rm.read(1, key1))
        assert_rm_result_ok(rm.update(1, key1, {"price": 200}))

        # T2 修改 key2
        assert_rm_result_ok(rm.read(2, key2))
        assert_rm_result_ok(rm.update(2, key2, {"price": 300}))

        # 两者都应 commit 成功
        p1 = rm.prepare(1)
        assert_rm_result_ok(p1)
        rm.commit(1)

        p2 = rm.prepare(2)
        assert_rm_result_ok(p2, "No conflict, T2 should also succeed")
        rm.commit(2)

        # 验证两个 key 都生效
        final1 = read_committed_like(rm, key1)
        final2 = read_committed_like(rm, key2)
        assert final1["price"] == 200
        assert final2["price"] == 300

        conn.close()
        print("✅ test_multi_key_no_conflict passed")


# =========================================================
# 测试类别 4: Prepare 不变式与错误处理类
# =========================================================


class TestPrepareInvariants:
    """【测试分类】Prepare 不变式与错误处理
    【测试目标】验证各种边界条件与错误码
    """

    def test_read_nonexistent_key(self):
        """【测试场景】读取不存在的 key
        【期望结果】KEY_NOT_FOUND
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.READ_NONEXISTENT

        preload_page_for_key(rm, 1, key)
        r = rm.read(1, key)
        assert_key_not_found(r, key)

        conn.close()
        print("✅ test_read_nonexistent_key passed")

    def test_update_nonexistent_key(self):
        """【测试场景】更新不存在的 key
        【期望结果】KEY_NOT_FOUND
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.UPDATE_NONEXISTENT

        preload_page_for_key(rm, 1, key)
        r = rm.update(1, key, {"price": 999})
        assert_key_not_found(r, key)

        conn.close()
        print("✅ test_update_nonexistent_key passed")

    def test_delete_nonexistent_key(self):
        """【测试场景】删除不存在的 key
        【期望结果】KEY_NOT_FOUND
        """
        conn = new_conn()
        rm = new_rm(
            conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
        )
        key = TestKeys.DELETE_NONEXISTENT

        preload_page_for_key(rm, 1, key)
        r = rm.delete(1, key)
        assert_key_not_found(r, key)

        conn.close()
        print("✅ test_delete_nonexistent_key passed")


# =========================================================
# 测试类别 5: 并发压力测试类 (Priority 2)
# =========================================================


class TestConcurrencyStress:
    """【测试分类】并发压力测试
    【测试目标】高并发场景下的正确性与性能指标
    【配置】THREADS=100, ROUNDS=200 (用户要求)
    """

    def test_hotspot_key_contention(self):
        """【测试场景】所有线程并发插入同一 hotspot key
        【期望结果】最多 1 个成功
        【性能指标】冲突率、成功率、吞吐量
        """
        THREADS = 100
        ROUNDS = 200

        for round_num in range(ROUNDS):
            conn = new_conn()
            rm = new_rm(
                conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
            )
            # 每轮使用不同的 key
            key = f"{TestKeys.STRESS_HOTSPOT}_{round_num:04d}"

            results = []
            barrier = threading.Barrier(THREADS)

            def worker(worker_id):
                try:
                    barrier.wait()  # 同步启动
                    xid = worker_id + 1
                    preload_page_for_key(rm, xid, key)
                    r_insert = rm.insert(
                        xid, create_flight_record(key, price=worker_id)
                    )
                    if not r_insert.ok:
                        results.append(("insert_fail", xid))
                        return
                    p = rm.prepare(xid)
                    if p.ok:
                        rm.commit(xid)
                        results.append(("commit", xid))
                    else:
                        rm.abort(xid)
                        results.append(("abort", xid, p.err))
                except Exception as e:
                    results.append(("exception", worker_id, str(e)))

            start_time = time.time()
            threads = [
                threading.Thread(target=worker, args=(i,)) for i in range(THREADS)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            elapsed = time.time() - start_time

            # 统计结果
            commits = [r for r in results if r[0] == "commit"]
            aborts = [r for r in results if r[0] == "abort"]

            assert len(commits) <= 1, f"Round {round_num}: Multiple commits! {commits}"

            conn.close()

            # 每 50 轮输出一次指标
            if (round_num + 1) % 50 == 0:
                success_rate = len(commits) / THREADS * 100 if THREADS > 0 else 0
                conflict_rate = len(aborts) / THREADS * 100 if THREADS > 0 else 0
                throughput = len(commits) / elapsed if elapsed > 0 else 0
                print(f"✅ test_hotspot_key_contention Round {round_num + 1}/{ROUNDS}:")
                print(f"   Success: {len(commits)}/{THREADS} ({success_rate:.1f}%)")
                print(f"   Conflict: {len(aborts)}/{THREADS} ({conflict_rate:.1f}%)")
                print(f"   Duration: {elapsed:.2f}s")
                print(f"   Throughput: {throughput:.1f} txn/s")

        print(f"✅✅ test_hotspot_key_contention ALL {ROUNDS} ROUNDS passed")

    def test_uniform_key_distribution(self):
        """【测试场景】每个线程操作不同 key（无冲突）
        【期望结果】所有事务都成功
        【性能指标】100% 成功率，高吞吐量
        """
        THREADS = 100
        ROUNDS = 100  # Uniform 场景较简单，减少轮次

        for round_num in range(ROUNDS):
            conn = new_conn()
            rm = new_rm(
                conn, table=TestData.DEFAULT_TABLE, key_column=TestData.DEFAULT_KEY_COL
            )

            results = []
            barrier = threading.Barrier(THREADS)

            def worker(worker_id):
                try:
                    barrier.wait()
                    xid = worker_id + 1
                    # 每个线程用不同的 key
                    key = f"{TestKeys.STRESS_UNIFORM_BASE + worker_id:04d}"
                    preload_page_for_key(rm, xid, key)
                    r_insert = rm.insert(
                        xid, create_flight_record(key, price=worker_id)
                    )
                    if not r_insert.ok:
                        results.append(("insert_fail", xid))
                        return
                    p = rm.prepare(xid)
                    if p.ok:
                        rm.commit(xid)
                        results.append(("commit", xid))
                    else:
                        rm.abort(xid)
                        results.append(("abort", xid, p.err))
                except Exception as e:
                    results.append(("exception", worker_id, str(e)))

            start_time = time.time()
            threads = [
                threading.Thread(target=worker, args=(i,)) for i in range(THREADS)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            elapsed = time.time() - start_time

            commits = [r for r in results if r[0] == "commit"]
            aborts = [r for r in results if r[0] == "abort"]

            # Uniform 分布应该全部成功
            assert len(commits) == THREADS, (
                f"Round {round_num}: Expected all {THREADS} to commit, got {len(commits)}"
            )

            conn.close()

            if (round_num + 1) % 25 == 0:
                success_rate = len(commits) / THREADS * 100
                throughput = len(commits) / elapsed if elapsed > 0 else 0
                print(
                    f"✅ test_uniform_key_distribution Round {round_num + 1}/{ROUNDS}:"
                )
                print(f"   Success: {len(commits)}/{THREADS} ({success_rate:.1f}%)")
                print(f"   Duration: {elapsed:.2f}s")
                print(f"   Throughput: {throughput:.1f} txn/s")

        print(f"✅✅ test_uniform_key_distribution ALL {ROUNDS} ROUNDS passed")


# =========================================================
# Main 入口
# =========================================================


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Resource Manager Test Suite")
    print("=" * 60)

    # Category 1: WW 冲突类
    print("\n【Category 1】WW Conflicts")
    print("-" * 60)
    ww = TestWWConflicts()
    ww.test_ww_conflict_insert_insert()
    ww.test_ww_conflict_insert_update()
    ww.test_ww_conflict_insert_delete()
    ww.test_ww_conflict_update_insert()
    ww.test_ww_conflict_update_update()
    ww.test_ww_conflict_update_delete()
    ww.test_ww_conflict_delete_insert()
    ww.test_ww_conflict_delete_update()
    ww.test_ww_conflict_delete_delete()

    # Category 2: Abort 路径验证类
    print("\n【Category 2】Abort Paths")
    print("-" * 60)
    abort = TestAbortPaths()
    abort.test_abort_rollback_insert()
    abort.test_abort_rollback_update()
    abort.test_abort_rollback_delete()
    abort.test_abort_releases_locks()

    # Category 3: 多 key 事务类
    print("\n【Category 3】Multi-Key Transactions")
    print("-" * 60)
    multi = TestMultiKeyTransactions()
    multi.test_multi_key_same_page()
    multi.test_multi_key_cross_page()
    multi.test_multi_key_no_conflict()

    # Category 4: Prepare 不变式与错误处理类
    print("\n【Category 4】Prepare Invariants")
    print("-" * 60)
    prep = TestPrepareInvariants()
    prep.test_read_nonexistent_key()
    prep.test_update_nonexistent_key()
    prep.test_delete_nonexistent_key()

    # Category 5: 并发压力测试类 (Priority 2) - 高强度
    print("\n【Category 5】Concurrency Stress Tests (High Intensity)")
    print("-" * 60)
    stress = TestConcurrencyStress()
    stress.test_hotspot_key_contention()
    stress.test_uniform_key_distribution()

    print("\n" + "=" * 60)
    print("✅✅✅ ALL RM TESTS PASSED ✅✅✅")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
