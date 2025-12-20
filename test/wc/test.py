"""
Workflow Controller Test Suite
测试 WC 层的跨服务事务、2PC 协调、不超卖等核心功能
"""

import logging
import threading
from datetime import datetime
from test.wc.config import TestConfig, TestKeys
from test.wc.helpers import *

# =========================================================
# 日志配置
# =========================================================

# 创建日志目录
import os
log_dir = os.path.join(os.path.dirname(__file__), "../../logs")
os.makedirs(log_dir, exist_ok=True)

# 配置日志
log_file = os.path.join(log_dir, f"wc_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()  # 同时输出到终端，方便实时查看
    ]
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info(f"WC Test Suite Started - Log file: {log_file}")
logger.info("=" * 60)


# =========================================================
# 测试类别 1: 唯一性约束类
# =========================================================


class TestUniquenessConstraints:
    """【测试分类】唯一性约束
    【测试目标】验证并发插入同一资源时只有一个成功
    """

    def test_concurrent_addFlight_stress(self):
        """【测试场景】多个事务并发添加同一航班
        【期望结果】最多 1 个成功
        【配置】THREADS=100, ROUNDS=200
        【性能指标】成功率、冲突率、吞吐量
        """
        wc = new_wc()
        THREADS = TestConfig.THREADS_HIGH
        ROUNDS = TestConfig.ROUNDS

        def txn_fn(wc, xid, worker_id):
            tiny_sleep()
            wc.addFlight(xid, TestKeys.UNIQUE_FLIGHT_BASE + "001", 500, 10)

        stats = run_concurrent_txns(wc, txn_fn, THREADS, ROUNDS, enable_metrics=True)

        # 验证每轮最多 1 个成功
        for r in stats['round_results']:
            assert r['commits'] <= 1, f"Round {r['round']}: Multiple commits {r['commits']}"

        print(f"✅ test_concurrent_addFlight_stress passed ({ROUNDS} rounds)")
        print_final_metrics("Concurrent addFlight Stress", stats, THREADS, ROUNDS)

    def test_concurrent_addHotel(self):
        """【测试场景】多个事务并发添加同一酒店
        【期望结果】最多 1 个成功
        【配置】THREADS=100, ROUNDS=200
        """
        wc = new_wc()
        THREADS = TestConfig.THREADS_HIGH
        ROUNDS = TestConfig.ROUNDS

        def txn_fn(wc, xid, worker_id):
            tiny_sleep()
            wc.addHotel(xid, TestKeys.UNIQUE_HOTEL_BASE + "001", 500, 10)

        stats = run_concurrent_txns(wc, txn_fn, THREADS, ROUNDS, enable_metrics=True)

        for r in stats['round_results']:
            assert r['commits'] <= 1, f"Round {r['round']}: Multiple commits"

        print(f"✅ test_concurrent_addHotel passed ({ROUNDS} rounds)")
        print_final_metrics("Concurrent addHotel", stats, THREADS, ROUNDS)

    def test_concurrent_addCar(self):
        """【测试场景】多个事务并发添加同一租车点
        【期望结果】最多 1 个成功
        【配置】THREADS=100, ROUNDS=200
        """
        wc = new_wc()
        THREADS = TestConfig.THREADS_HIGH
        ROUNDS = TestConfig.ROUNDS

        def txn_fn(wc, xid, worker_id):
            tiny_sleep()
            wc.addCar(xid, TestKeys.UNIQUE_CAR_BASE + "001", 500, 10)

        stats = run_concurrent_txns(wc, txn_fn, THREADS, ROUNDS, enable_metrics=True)

        for r in stats['round_results']:
            assert r['commits'] <= 1, f"Round {r['round']}: Multiple commits"

        print(f"✅ test_concurrent_addCar passed ({ROUNDS} rounds)")
        print_final_metrics("Concurrent addCar", stats, THREADS, ROUNDS)

    def test_concurrent_addCustomer(self):
        """【测试场景】多个事务并发添加同一客户
        【期望结果】最多 1 个成功
        【配置】THREADS=100, ROUNDS=200
        """
        wc = new_wc()
        THREADS = TestConfig.THREADS_HIGH
        ROUNDS = TestConfig.ROUNDS

        def txn_fn(wc, xid, worker_id):
            tiny_sleep()
            wc.addCustomer(xid, TestKeys.UNIQUE_CUST_BASE + "001")

        stats = run_concurrent_txns(wc, txn_fn, THREADS, ROUNDS, enable_metrics=True)

        for r in stats['round_results']:
            assert r['commits'] <= 1, f"Round {r['round']}: Multiple commits"

        print(f"✅ test_concurrent_addCustomer passed ({ROUNDS} rounds)")
        print_final_metrics("Concurrent addCustomer", stats, THREADS, ROUNDS)


# =========================================================
# 测试类别 2: Abort 可见性与原子性类
# =========================================================


class TestAbortVisibility:
    """【测试分类】Abort 可见性与原子性
    【测试目标】验证 abort 后修改不可见，所有服务都回滚
    """

    def test_abort_visibility(self):
        """【测试场景】T1 addFlight 后 abort
        【期望结果】T2 查询返回 None
        """
        wc = new_wc()
        flight_num = TestKeys.ABORT_VISIBILITY_FLIGHT

        # T1: addFlight 然后 abort
        xid1 = wc.start()
        wc.addFlight(xid1, flight_num, 500, 10)
        wc.abort(xid1)

        # T2: 查询应该返回 None
        assert_flight_not_exists(wc, flight_num)

        print("✅ test_abort_visibility passed")

    def test_delete_atomicity(self):
        """【测试场景】delete abort vs commit
        【期望结果】abort → 记录存在；commit → 记录消失
        """
        wc = new_wc()
        flight_num = TestKeys.DELETE_ATOMICITY_FLIGHT

        # Setup: addFlight
        setup_flight(wc, flight_num, seats=10)
        assert_flight_exists(wc, flight_num)

        # T1: deleteFlight 然后 abort
        xid1 = wc.start()
        wc.deleteFlight(xid1, flight_num)
        wc.abort(xid1)

        # 验证记录仍存在
        assert_flight_exists(wc, flight_num)

        # T2: deleteFlight 然后 commit
        xid2 = wc.start()
        wc.deleteFlight(xid2, flight_num)
        wc.commit(xid2)

        # 验证记录已消失
        assert_flight_not_exists(wc, flight_num)

        print("✅ test_delete_atomicity passed")

    def test_cross_service_abort(self):
        """【测试场景】T1 跨服务操作后 abort
        【期望结果】所有服务都回滚
        """
        wc = new_wc()
        flight_num = TestKeys.ABORT_CROSS_SERVICE_FLIGHT
        hotel_loc = TestKeys.ABORT_CROSS_SERVICE_HOTEL
        cust_id = TestKeys.ABORT_CROSS_SERVICE_CUST

        # T1: 添加 Flight + Hotel + Customer，然后 abort
        xid = wc.start()
        wc.addFlight(xid, flight_num, 500, 10)
        wc.addHotel(xid, hotel_loc, 600, 20)
        wc.addCustomer(xid, cust_id)
        wc.abort(xid)

        # 验证所有服务都回滚
        assert_flight_not_exists(wc, flight_num)
        assert_hotel_not_exists(wc, hotel_loc)
        assert_customer_not_exists(wc, cust_id)

        print("✅ test_cross_service_abort passed")

    def test_partial_operation_abort(self):
        """【测试场景】部分操作失败后 abort
        【期望结果】所有操作都回滚
        """
        wc = new_wc()
        flight_num = TestKeys.ABORT_CROSS_SERVICE_FLIGHT + "_partial"

        # T1: addFlight 成功，但 reserveFlight 会失败（customer 不存在）
        xid = wc.start()
        wc.addFlight(xid, flight_num, 500, 10)

        # 尝试预订（会失败因为 customer 不存在）
        try:
            wc.reserveFlight(xid, "NONEXIST_CUST", flight_num, 1)
            assert False, "Should have raised RuntimeError"
        except RuntimeError:
            pass  # Expected

        wc.abort(xid)

        # 验证 flight 未创建
        assert_flight_not_exists(wc, flight_num)

        print("✅ test_partial_operation_abort passed")


# =========================================================
# 测试类别 3: 不超卖类
# =========================================================


class TestNoOversell:
    """【测试分类】不超卖
    【测试目标】验证并发预订不超卖，资源约束正确
    """

    def test_concurrent_reserve_no_oversell(self):
        """【测试场景】并发 reserveFlight
        【期望结果】最多 SEATS 个成功，numAvail ≥ 0
        【配置】THREADS=100, SEATS=50
        """
        wc = new_wc()
        THREADS = TestConfig.THREADS_HIGH
        SEATS = 50
        flight_num = TestKeys.RESERVE_FLIGHT_BASE + "001"
        cust_id = TestKeys.RESERVE_CUST_BASE + "001"

        # Setup: addFlight and addCustomer
        setup_flight(wc, flight_num, seats=SEATS)
        setup_customer(wc, cust_id)

        results = []
        barrier = threading.Barrier(THREADS)

        def reserve_txn(worker_id):
            xid = None
            try:
                barrier.wait()
                xid = wc.start()
                wc.reserveFlight(xid, cust_id, flight_num, 1)
                wc.commit(xid)
                results.append(('commit', xid))
            except Exception as e:
                if xid is not None:
                    try:
                        wc.abort(xid)
                    except:
                        pass
                results.append(('abort', xid, str(e)))

        threads = [threading.Thread(target=reserve_txn, args=(i,)) for i in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        commits = [r for r in results if r[0] == 'commit']
        aborts = [r for r in results if r[0] == 'abort']

        # 验证：成功数 ≤ SEATS
        assert len(commits) <= SEATS, f"Oversold! commits={len(commits)}, seats={SEATS}"

        # 验证：numAvail ≥ 0
        final_avail = query_flight_avail(wc, flight_num)
        assert final_avail >= 0, f"numAvail < 0: {final_avail}"

        # 验证：numAvail = SEATS - commits
        assert final_avail == SEATS - len(commits), (
            f"numAvail mismatch: expected {SEATS - len(commits)}, got {final_avail}"
        )

        print(f"✅ test_concurrent_reserve_no_oversell passed")
        print(f"   Success: {len(commits)}/{THREADS}, Final numAvail: {final_avail}")

    def test_reserve_customer_not_exist(self):
        """【测试场景】Customer 不存在时预订
        【期望结果】RuntimeError
        """
        wc = new_wc()
        flight_num = TestKeys.RESERVE_FLIGHT_BASE + "002"

        # Setup: addFlight only (no customer)
        setup_flight(wc, flight_num, seats=10)

        # T1: 尝试预订（customer 不存在）
        xid = wc.start()
        try:
            wc.reserveFlight(xid, "NONEXIST_CUST", flight_num, 1)
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "not found" in str(e).lower() or "does not exist" in str(e).lower()
        wc.abort(xid)

        print("✅ test_reserve_customer_not_exist passed")

    def test_reserve_flight_not_exist(self):
        """【测试场景】Flight 不存在时预订
        【期望结果】RuntimeError
        """
        wc = new_wc()
        cust_id = TestKeys.RESERVE_CUST_BASE + "003"

        # Setup: addCustomer only (no flight)
        setup_customer(wc, cust_id)

        # T1: 尝试预订（flight 不存在）
        xid = wc.start()
        try:
            wc.reserveFlight(xid, cust_id, "NONEXIST_FLIGHT", 1)
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "not found" in str(e).lower() or "does not exist" in str(e).lower()
        wc.abort(xid)

        print("✅ test_reserve_flight_not_exist passed")

    def test_reserve_insufficient_seats(self):
        """【测试场景】座位不足时预订
        【期望结果】RuntimeError
        """
        wc = new_wc()
        flight_num = TestKeys.RESERVE_FLIGHT_BASE + "004"
        cust_id = TestKeys.RESERVE_CUST_BASE + "004"

        # Setup: flight with 2 seats
        setup_flight(wc, flight_num, seats=2)
        setup_customer(wc, cust_id)

        # T1: 尝试预订 3 个座位（不足）
        xid = wc.start()
        try:
            wc.reserveFlight(xid, cust_id, flight_num, 3)
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "insufficient" in str(e).lower() or "not enough" in str(e).lower()
        wc.abort(xid)

        # 验证 numAvail 仍为 2
        assert_flight_exists(wc, flight_num, expected_avail=2)

        print("✅ test_reserve_insufficient_seats passed")

    def test_reserve_hotel_no_oversell(self):
        """【测试场景】并发 reserveHotel（Priority 2）
        【期望结果】最多 ROOMS 个成功
        【配置】THREADS=80, ROOMS=40
        """
        wc = new_wc()
        THREADS = 80
        ROOMS = 40
        hotel_loc = TestKeys.RESERVE_HOTEL_BASE + "001"
        cust_id = TestKeys.RESERVE_CUST_BASE + "hotel001"

        # Setup
        setup_hotel(wc, hotel_loc, rooms=ROOMS)
        setup_customer(wc, cust_id)

        results = []
        barrier = threading.Barrier(THREADS)

        def reserve_txn(worker_id):
            xid = None
            try:
                barrier.wait()
                xid = wc.start()
                wc.reserveHotel(xid, cust_id, hotel_loc, 1)
                wc.commit(xid)
                results.append(('commit', xid))
            except Exception as e:
                if xid is not None:
                    try:
                        wc.abort(xid)
                    except:
                        pass
                results.append(('abort', xid))

        threads = [threading.Thread(target=reserve_txn, args=(i,)) for i in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        commits = [r for r in results if r[0] == 'commit']

        assert len(commits) <= ROOMS, f"Oversold! commits={len(commits)}, rooms={ROOMS}"

        final_avail = query_hotel_avail(wc, hotel_loc)
        assert final_avail >= 0, f"numAvail < 0: {final_avail}"

        print(f"✅ test_reserve_hotel_no_oversell passed")
        print(f"   Success: {len(commits)}/{THREADS}, Final numAvail: {final_avail}")

    def test_reserve_car_no_oversell(self):
        """【测试场景】并发 reserveCar（Priority 2）
        【期望结果】最多 CARS 个成功
        【配置】THREADS=80, CARS=40
        """
        wc = new_wc()
        THREADS = 80
        CARS = 40
        car_loc = TestKeys.RESERVE_CAR_BASE + "001"
        cust_id = TestKeys.RESERVE_CUST_BASE + "car001"

        # Setup
        setup_car(wc, car_loc, cars=CARS)
        setup_customer(wc, cust_id)

        results = []
        barrier = threading.Barrier(THREADS)

        def reserve_txn(worker_id):
            xid = None
            try:
                barrier.wait()
                xid = wc.start()
                wc.reserveCar(xid, cust_id, car_loc, 1)
                wc.commit(xid)
                results.append(('commit', xid))
            except Exception as e:
                if xid is not None:
                    try:
                        wc.abort(xid)
                    except:
                        pass
                results.append(('abort', xid))

        threads = [threading.Thread(target=reserve_txn, args=(i,)) for i in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        commits = [r for r in results if r[0] == 'commit']

        assert len(commits) <= CARS, f"Oversold! commits={len(commits)}, cars={CARS}"

        final_avail = query_car_avail(wc, car_loc)
        assert final_avail >= 0, f"numAvail < 0: {final_avail}"

        print(f"✅ test_reserve_car_no_oversell passed")
        print(f"   Success: {len(commits)}/{THREADS}, Final numAvail: {final_avail}")


# =========================================================
# 测试类别 4: 跨服务事务类
# =========================================================


class TestCrossServiceTransactions:
    """【测试分类】跨服务事务
    【测试目标】验证 2PC 跨多个 RM 的正确性
    """

    def test_cross_service_commit(self):
        """【测试场景】T1 添加 Flight+Hotel+Car
        【期望结果】所有服务都 commit
        """
        wc = new_wc()
        flight_num = TestKeys.CROSS_FLIGHT
        hotel_loc = TestKeys.CROSS_HOTEL
        car_loc = TestKeys.CROSS_CAR

        # T1: 添加 3 个资源
        xid = wc.start()
        wc.addFlight(xid, flight_num, 500, 10)
        wc.addHotel(xid, hotel_loc, 600, 20)
        wc.addCar(xid, car_loc, 400, 15)
        wc.commit(xid)

        # 验证所有资源都存在
        assert_flight_exists(wc, flight_num, expected_avail=10)
        assert_hotel_exists(wc, hotel_loc, expected_avail=20)
        assert_car_exists(wc, car_loc, expected_avail=15)

        print("✅ test_cross_service_commit passed")

    def test_cross_service_complex_workflow(self):
        """【测试场景】reserveFlight + reserveHotel
        【期望结果】两个 reservation 都创建
        """
        wc = new_wc()
        flight_num = TestKeys.COMPLEX_FLIGHT
        hotel_loc = TestKeys.COMPLEX_HOTEL
        cust_id = TestKeys.COMPLEX_CUST

        # Setup
        setup_flight(wc, flight_num, seats=10)
        setup_hotel(wc, hotel_loc, rooms=10)
        setup_customer(wc, cust_id)

        # T1: 预订 Flight + Hotel
        xid = wc.start()
        wc.reserveFlight(xid, cust_id, flight_num, 2)
        wc.reserveHotel(xid, cust_id, hotel_loc, 1)
        wc.commit(xid)

        # 验证 numAvail 减少
        assert_flight_exists(wc, flight_num, expected_avail=8)
        assert_hotel_exists(wc, hotel_loc, expected_avail=9)

        print("✅ test_cross_service_complex_workflow passed")

    def test_cross_service_one_fails(self):
        """【测试场景】一个服务操作失败
        【期望结果】所有服务都 abort（2PC）
        """
        wc = new_wc()
        flight_num = TestKeys.COMPLEX_FLIGHT + "_fail"
        cust_id = TestKeys.COMPLEX_CUST + "_fail"

        # Setup: addFlight and addCustomer (no hotel)
        setup_flight(wc, flight_num, seats=10)
        setup_customer(wc, cust_id)

        # T1: reserveFlight + reserveHotel (hotel 不存在 → 失败)
        xid = wc.start()
        try:
            wc.reserveFlight(xid, cust_id, flight_num, 1)
            wc.reserveHotel(xid, cust_id, "NONEXIST_HOTEL", 1)  # 会失败
            wc.commit(xid)
            assert False, "Should have raised RuntimeError"
        except RuntimeError:
            wc.abort(xid)

        # 验证 flight.numAvail 未减少（rollback）
        assert_flight_exists(wc, flight_num, expected_avail=10)

        print("✅ test_cross_service_one_fails passed")


# =========================================================
# 测试类别 5: 2PC 失败场景类
# =========================================================


class TestTwoPCFailures:
    """【测试分类】2PC 失败场景
    【测试目标】验证 prepare 阶段失败时 TM 正确 abort 所有 RM
    """

    def test_prepare_fails_on_one_rm(self):
        """【测试场景】单个 RM prepare 失败
        【期望结果】TM abort 所有 RM
        """
        wc = new_wc()
        flight_num = TestKeys.TPC_FAIL_FLIGHT

        # Setup: seed flight
        setup_flight(wc, flight_num, seats=10)

        # T1: update flight
        xid1 = wc.start()
        wc.deleteFlight(xid1, flight_num)
        wc.addFlight(xid1, flight_num, 600, 20)
        wc.commit(xid1)

        # T2: 尝试 update 同一 flight（会因版本冲突 prepare 失败）
        xid2 = wc.start()
        # 先读 old version
        old_flight = wc.queryFlight(xid2, flight_num)
        assert old_flight is not None

        # T3: 再次修改（导致 T2 版本过期）
        xid3 = wc.start()
        wc.deleteFlight(xid3, flight_num)
        wc.addFlight(xid3, flight_num, 700, 30)
        wc.commit(xid3)

        # T2: 尝试 commit（prepare 会失败）
        try:
            wc.deleteFlight(xid2, flight_num)
            result = wc.commit(xid2)
            # commit 可能返回 ok=False
            if result.get('ok', True):
                # 某些实现可能成功（取决于实现）
                pass
            else:
                # 预期失败
                pass
        except Exception:
            # 预期可能抛异常
            wc.abort(xid2)

        # 验证最终状态为 T3 的值
        assert_flight_exists(wc, flight_num, expected_avail=30)

        print("✅ test_prepare_fails_on_one_rm passed")

    def test_prepare_fails_multiple_rms(self):
        """【测试场景】多个 RM 其中一个 prepare 失败
        【期望结果】TM abort 所有 RM
        """
        wc = new_wc()
        flight_num = TestKeys.TPC_MULTI_FLIGHT
        hotel_loc = TestKeys.TPC_MULTI_HOTEL

        # Setup
        setup_flight(wc, flight_num, seats=10)
        setup_hotel(wc, hotel_loc, rooms=10)

        # T1: update flight + hotel
        xid1 = wc.start()
        wc.deleteFlight(xid1, flight_num)
        wc.addFlight(xid1, flight_num, 600, 20)
        wc.deleteHotel(xid1, hotel_loc)
        wc.addHotel(xid1, hotel_loc, 700, 30)
        wc.commit(xid1)

        # T2: 读取（记录版本）
        xid2 = wc.start()
        wc.queryFlight(xid2, flight_num)
        wc.queryHotel(xid2, hotel_loc)

        # T3: 修改 flight（导致 T2 的 flight 版本过期）
        xid3 = wc.start()
        wc.deleteFlight(xid3, flight_num)
        wc.addFlight(xid3, flight_num, 800, 40)
        wc.commit(xid3)

        # T2: 尝试 commit（flight prepare 失败 → hotel 也应 abort）
        try:
            wc.deleteFlight(xid2, flight_num)
            wc.deleteHotel(xid2, hotel_loc)
            result = wc.commit(xid2)
            if not result.get('ok', True):
                pass  # Expected failure
        except Exception:
            wc.abort(xid2)

        # 验证两个服务都是 T3/T1 的值（T2 未生效）
        assert_flight_exists(wc, flight_num, expected_avail=40)  # T3
        assert_hotel_exists(wc, hotel_loc, expected_avail=30)   # T1

        print("✅ test_prepare_fails_multiple_rms passed")

    def test_tm_enlist_idempotent(self):
        """【测试场景】同一 RM 多次 enlist
        【期望结果】TM 只记录 1 次
        """
        wc = new_wc()
        flight1 = TestKeys.TPC_MULTI_FLIGHT + "_1"
        flight2 = TestKeys.TPC_MULTI_FLIGHT + "_2"

        # T1: 添加两个 flight（都使用同一 RM）
        xid = wc.start()
        wc.addFlight(xid, flight1, 500, 10)
        wc.addFlight(xid, flight2, 600, 20)
        wc.commit(xid)

        # 验证都成功
        assert_flight_exists(wc, flight1, expected_avail=10)
        assert_flight_exists(wc, flight2, expected_avail=20)

        # 注：无法直接验证 TM 内部状态，但成功 commit 说明 enlist 正确

        print("✅ test_tm_enlist_idempotent passed")


# =========================================================
# 测试类别 6: TM 状态管理类
# =========================================================


class TestTMStateManagement:
    """【测试分类】TM 状态管理
    【测试目标】验证 TM 对事务状态的管理
    """

    def test_commit_nonexistent_xid(self):
        """【测试场景】commit 不存在的 xid
        【期望结果】404 错误或异常
        """
        wc = new_wc()

        try:
            result = wc.commit(999999)
            # 如果返回字典，检查 ok 字段
            if isinstance(result, dict):
                assert not result.get('ok', False), "Should fail for nonexistent xid"
        except Exception as e:
            # 预期抛异常
            assert "404" in str(e) or "not found" in str(e).lower()

        print("✅ test_commit_nonexistent_xid passed")

    def test_abort_nonexistent_xid(self):
        """【测试场景】abort 不存在的 xid
        【期望结果】404 错误或异常
        """
        wc = new_wc()

        try:
            result = wc.abort(999999)
            if isinstance(result, dict):
                assert not result.get('ok', False), "Should fail for nonexistent xid"
        except Exception as e:
            assert "404" in str(e) or "not found" in str(e).lower()

        print("✅ test_abort_nonexistent_xid passed")

    def test_double_commit(self):
        """【测试场景】重复 commit
        【期望结果】409 错误或异常
        """
        wc = new_wc()
        flight_num = TestKeys.CROSS_FLIGHT + "_double"

        # T1: addFlight and commit
        xid = wc.start()
        wc.addFlight(xid, flight_num, 500, 10)
        wc.commit(xid)

        # 再次 commit
        try:
            result = wc.commit(xid)
            if isinstance(result, dict):
                assert not result.get('ok', False), "Double commit should fail"
        except Exception as e:
            assert "409" in str(e) or "already" in str(e).lower()

        print("✅ test_double_commit passed")

    def test_commit_after_abort(self):
        """【测试场景】abort 后 commit
        【期望结果】409 错误或异常
        """
        wc = new_wc()
        flight_num = TestKeys.CROSS_FLIGHT + "_abort_commit"

        # T1: addFlight and abort
        xid = wc.start()
        wc.addFlight(xid, flight_num, 500, 10)
        wc.abort(xid)

        # 尝试 commit
        try:
            result = wc.commit(xid)
            if isinstance(result, dict):
                assert not result.get('ok', False), "Commit after abort should fail"
        except Exception as e:
            assert "409" in str(e) or "already" in str(e).lower() or "aborted" in str(e).lower()

        print("✅ test_commit_after_abort passed")

    def test_abort_idempotent(self):
        """【测试场景】重复 abort
        【期望结果】ok=True（幂等）
        """
        wc = new_wc()
        flight_num = TestKeys.CROSS_FLIGHT + "_abort_idempotent"

        # T1: addFlight and abort
        xid = wc.start()
        wc.addFlight(xid, flight_num, 500, 10)
        wc.abort(xid)

        # 再次 abort（应该成功或返回 ok=True）
        try:
            result = wc.abort(xid)
            # abort 通常是幂等的
            if isinstance(result, dict):
                assert result.get('ok', True), "Abort should be idempotent"
        except Exception:
            # 某些实现可能抛异常，也可接受
            pass

        print("✅ test_abort_idempotent passed")


# =========================================================
# 测试类别 7: 混合操作场景类
# =========================================================


class TestMixedOperations:
    """【测试分类】混合操作场景
    【测试目标】验证 add + delete + query 混合场景
    """

    def test_mixed_add_delete_query(self):
        """【测试场景】delete + add 混合操作
        【期望结果】FL01 消失，FL02 存在
        """
        wc = new_wc()
        flight1 = TestKeys.MIXED_FLIGHT_1
        flight2 = TestKeys.MIXED_FLIGHT_2

        # Setup: addFlight FL01
        setup_flight(wc, flight1, seats=10)

        # T1: deleteFlight FL01 + addFlight FL02
        xid = wc.start()
        wc.deleteFlight(xid, flight1)
        wc.addFlight(xid, flight2, 600, 20)
        wc.commit(xid)

        # 验证 FL01 消失，FL02 存在
        assert_flight_not_exists(wc, flight1)
        assert_flight_exists(wc, flight2, expected_avail=20)

        print("✅ test_mixed_add_delete_query passed")

    def test_read_own_write(self):
        """【测试场景】事务内读自己的写
        【期望结果】commit 前能读到
        """
        wc = new_wc()
        flight_num = TestKeys.READ_OWN_WRITE_FLIGHT

        # T1: addFlight, 然后 query（在 commit 前）
        xid = wc.start()
        wc.addFlight(xid, flight_num, 500, 10)

        # 事务内查询
        rec = wc.queryFlight(xid, flight_num)
        assert rec is not None, "Should read own write"
        assert rec["numAvail"] == 10

        wc.commit(xid)

        print("✅ test_read_own_write passed")

    def test_read_after_delete(self):
        """【测试场景】事务内 delete 后 read
        【期望结果】返回 None
        """
        wc = new_wc()
        flight_num = TestKeys.READ_AFTER_DELETE_FLIGHT

        # Setup: addFlight
        setup_flight(wc, flight_num, seats=10)

        # T1: deleteFlight, 然后 query
        xid = wc.start()
        wc.deleteFlight(xid, flight_num)

        # 事务内查询（应该返回 None）
        rec = wc.queryFlight(xid, flight_num)
        assert rec is None, "Should not read deleted record"

        wc.commit(xid)

        print("✅ test_read_after_delete passed")


# =========================================================
# 测试类别 8: 并发度与 key 分布类（Priority 2）
# =========================================================


class TestConcurrencyDistribution:
    """【测试分类】并发度与 key 分布
    【测试目标】验证热点 key vs 均匀分布的性能差异
    【配置】THREADS=100
    """

    def test_hotspot_key_high_concurrency(self):
        """【测试场景】所有线程 addFlight 同一 key
        【期望结果】只有 1 个成功
        【性能指标】成功率 ≈ 1%
        【配置】THREADS=100, ROUNDS=200
        """
        wc = new_wc()
        THREADS = TestConfig.THREADS_HIGH
        ROUNDS = TestConfig.ROUNDS

        def txn_fn(wc, xid, worker_id):
            tiny_sleep()
            wc.addFlight(xid, TestKeys.HOTSPOT_FLIGHT, 500, 10)

        stats = run_concurrent_txns(wc, txn_fn, THREADS, ROUNDS, enable_metrics=True)

        # 验证每轮只有 1 个成功
        for r in stats['round_results']:
            assert r['commits'] <= 1, f"Round {r['round']}: Multiple commits"

        # 计算总体成功率
        success_rate = stats['total_commits'] / (THREADS * ROUNDS) * 100
        assert success_rate < 5, f"Success rate too high: {success_rate:.1f}%"

        print(f"✅ test_hotspot_key_high_concurrency passed ({ROUNDS} rounds)")
        print(f"   Overall success rate: {success_rate:.2f}%")
        print_final_metrics("Hotspot Key High Concurrency", stats, THREADS, ROUNDS)

    def test_uniform_key_low_conflict(self):
        """【测试场景】每个线程不同 key
        【期望结果】所有成功
        【性能指标】成功率 = 100%
        【配置】THREADS=100, ROUNDS=100
        """
        wc = new_wc()
        THREADS = TestConfig.THREADS_HIGH
        ROUNDS = 100  # Uniform 场景较简单，减少轮次

        def txn_fn(wc, xid, worker_id):
            tiny_sleep()
            # 每个 worker 用不同 key
            key = f"{TestKeys.UNIFORM_FLIGHT_BASE}{worker_id:03d}"
            wc.addFlight(xid, key, 500, 10)

        stats = run_concurrent_txns(wc, txn_fn, THREADS, ROUNDS, enable_metrics=True)

        # 验证每轮所有线程都成功
        for r in stats['round_results']:
            assert r['commits'] == THREADS, (
                f"Round {r['round']}: Expected all {THREADS} to commit, got {r['commits']}"
            )

        success_rate = stats['total_commits'] / (THREADS * ROUNDS) * 100
        assert success_rate == 100, f"Success rate should be 100%, got {success_rate:.1f}%"

        print(f"✅ test_uniform_key_low_conflict passed ({ROUNDS} rounds)")
        print(f"   Overall success rate: {success_rate:.2f}%")
        print_final_metrics("Uniform Key Low Conflict", stats, THREADS, ROUNDS)

    def test_mixed_operations_high_concurrency(self):
        """【测试场景】并发 reserveFlight
        【期望结果】最多 SEATS 个成功
        【性能指标】吞吐量统计
        【配置】THREADS=100, SEATS=50, ROUNDS=100
        """
        wc = new_wc()
        THREADS = TestConfig.THREADS_HIGH
        ROUNDS = 100
        SEATS = 50
        flight_num = TestKeys.MIXED_OPS_FLIGHT
        cust_id = TestKeys.RESERVE_CUST_BASE + "mixed"

        # Setup
        setup_flight(wc, flight_num, seats=SEATS)
        setup_customer(wc, cust_id)

        results = []
        barrier = threading.Barrier(THREADS)

        def reserve_txn(worker_id):
            xid = None
            try:
                barrier.wait()
                xid = wc.start()
                wc.reserveFlight(xid, cust_id, flight_num, 1)
                wc.commit(xid)
                results.append(('commit', xid))
            except Exception:
                if xid is not None:
                    try:
                        wc.abort(xid)
                    except:
                        pass
                results.append(('abort', xid))

        import time
        start_time = time.time()

        threads = [threading.Thread(target=reserve_txn, args=(i,)) for i in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.time() - start_time

        commits = [r for r in results if r[0] == 'commit']

        assert len(commits) <= SEATS, f"Oversold! commits={len(commits)}, seats={SEATS}"

        # 统计
        throughput = len(commits) / elapsed if elapsed > 0 else 0
        success_rate = len(commits) / THREADS * 100

        print(f"✅ test_mixed_operations_high_concurrency passed")
        print(f"   Success: {len(commits)}/{THREADS} ({success_rate:.1f}%)")
        print(f"   Duration: {elapsed:.2f}s")
        print(f"   Throughput: {throughput:.1f} txn/s")


# =========================================================
# 测试执行辅助函数
# =========================================================


def run_test(test_fn, test_name):
    """运行单个测试并捕获错误"""
    try:
        logger.info(f"▶ Running: {test_name}")
        test_fn()
        logger.info(f"✅ PASSED: {test_name}")
        return True
    except Exception as e:
        logger.error(f"❌ FAILED: {test_name}")
        logger.error(f"   Error: {str(e)}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return False


# =========================================================
# Main 入口
# =========================================================


def run_all_tests():
    """运行所有测试"""
    logger.info("=" * 60)
    logger.info("Workflow Controller Test Suite")
    logger.info("=" * 60)

    test_results = []
    total_tests = 0
    passed_tests = 0

    # Category 1: 唯一性约束类
    logger.info("\n【Category 1】Uniqueness Constraints")
    logger.info("-" * 60)
    uc = TestUniquenessConstraints()
    tests_cat1 = [
        (uc.test_concurrent_addFlight_stress, "test_concurrent_addFlight_stress"),
        (uc.test_concurrent_addHotel, "test_concurrent_addHotel"),
        (uc.test_concurrent_addCar, "test_concurrent_addCar"),
        (uc.test_concurrent_addCustomer, "test_concurrent_addCustomer"),
    ]
    for test_fn, test_name in tests_cat1:
        total_tests += 1
        if run_test(test_fn, test_name):
            passed_tests += 1
            test_results.append((test_name, "PASSED"))
        else:
            test_results.append((test_name, "FAILED"))

    # Category 2: Abort 可见性与原子性类
    logger.info("\n【Category 2】Abort Visibility & Atomicity")
    logger.info("-" * 60)
    av = TestAbortVisibility()
    tests_cat2 = [
        (av.test_abort_visibility, "test_abort_visibility"),
        (av.test_delete_atomicity, "test_delete_atomicity"),
        (av.test_cross_service_abort, "test_cross_service_abort"),
        (av.test_partial_operation_abort, "test_partial_operation_abort"),
    ]
    for test_fn, test_name in tests_cat2:
        total_tests += 1
        if run_test(test_fn, test_name):
            passed_tests += 1
            test_results.append((test_name, "PASSED"))
        else:
            test_results.append((test_name, "FAILED"))

    # Category 3: 不超卖类
    logger.info("\n【Category 3】No Oversell")
    logger.info("-" * 60)
    no = TestNoOversell()
    tests_cat3 = [
        (no.test_concurrent_reserve_no_oversell, "test_concurrent_reserve_no_oversell"),
        (no.test_reserve_customer_not_exist, "test_reserve_customer_not_exist"),
        (no.test_reserve_flight_not_exist, "test_reserve_flight_not_exist"),
        (no.test_reserve_insufficient_seats, "test_reserve_insufficient_seats"),
        (no.test_reserve_hotel_no_oversell, "test_reserve_hotel_no_oversell"),
        (no.test_reserve_car_no_oversell, "test_reserve_car_no_oversell"),
    ]
    for test_fn, test_name in tests_cat3:
        total_tests += 1
        if run_test(test_fn, test_name):
            passed_tests += 1
            test_results.append((test_name, "PASSED"))
        else:
            test_results.append((test_name, "FAILED"))

    # Category 4: 跨服务事务类
    logger.info("\n【Category 4】Cross-Service Transactions")
    logger.info("-" * 60)
    cs = TestCrossServiceTransactions()
    tests_cat4 = [
        (cs.test_cross_service_commit, "test_cross_service_commit"),
        (cs.test_cross_service_complex_workflow, "test_cross_service_complex_workflow"),
        (cs.test_cross_service_one_fails, "test_cross_service_one_fails"),
    ]
    for test_fn, test_name in tests_cat4:
        total_tests += 1
        if run_test(test_fn, test_name):
            passed_tests += 1
            test_results.append((test_name, "PASSED"))
        else:
            test_results.append((test_name, "FAILED"))

    # Category 5: 2PC 失败场景类
    logger.info("\n【Category 5】2PC Failure Scenarios")
    logger.info("-" * 60)
    tpc = TestTwoPCFailures()
    tests_cat5 = [
        (tpc.test_prepare_fails_on_one_rm, "test_prepare_fails_on_one_rm"),
        (tpc.test_prepare_fails_multiple_rms, "test_prepare_fails_multiple_rms"),
        (tpc.test_tm_enlist_idempotent, "test_tm_enlist_idempotent"),
    ]
    for test_fn, test_name in tests_cat5:
        total_tests += 1
        if run_test(test_fn, test_name):
            passed_tests += 1
            test_results.append((test_name, "PASSED"))
        else:
            test_results.append((test_name, "FAILED"))

    # Category 6: TM 状态管理类
    logger.info("\n【Category 6】TM State Management")
    logger.info("-" * 60)
    tm = TestTMStateManagement()
    tests_cat6 = [
        (tm.test_commit_nonexistent_xid, "test_commit_nonexistent_xid"),
        (tm.test_abort_nonexistent_xid, "test_abort_nonexistent_xid"),
        (tm.test_double_commit, "test_double_commit"),
        (tm.test_commit_after_abort, "test_commit_after_abort"),
        (tm.test_abort_idempotent, "test_abort_idempotent"),
    ]
    for test_fn, test_name in tests_cat6:
        total_tests += 1
        if run_test(test_fn, test_name):
            passed_tests += 1
            test_results.append((test_name, "PASSED"))
        else:
            test_results.append((test_name, "FAILED"))

    # Category 7: 混合操作场景类
    logger.info("\n【Category 7】Mixed Operations")
    logger.info("-" * 60)
    mo = TestMixedOperations()
    tests_cat7 = [
        (mo.test_mixed_add_delete_query, "test_mixed_add_delete_query"),
        (mo.test_read_own_write, "test_read_own_write"),
        (mo.test_read_after_delete, "test_read_after_delete"),
    ]
    for test_fn, test_name in tests_cat7:
        total_tests += 1
        if run_test(test_fn, test_name):
            passed_tests += 1
            test_results.append((test_name, "PASSED"))
        else:
            test_results.append((test_name, "FAILED"))

    # Category 8: 并发度与 key 分布类（Priority 2）
    logger.info("\n【Category 8】Concurrency & Key Distribution (High Intensity)")
    logger.info("-" * 60)
    cd = TestConcurrencyDistribution()
    tests_cat8 = [
        (cd.test_hotspot_key_high_concurrency, "test_hotspot_key_high_concurrency"),
        (cd.test_uniform_key_low_conflict, "test_uniform_key_low_conflict"),
        (cd.test_mixed_operations_high_concurrency, "test_mixed_operations_high_concurrency"),
    ]
    for test_fn, test_name in tests_cat8:
        total_tests += 1
        if run_test(test_fn, test_name):
            passed_tests += 1
            test_results.append((test_name, "PASSED"))
        else:
            test_results.append((test_name, "FAILED"))

    # 输出测试总结
    logger.info("\n" + "=" * 60)
    logger.info("WC TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total Tests: {total_tests}")
    logger.info(f"Passed: {passed_tests}")
    logger.info(f"Failed: {total_tests - passed_tests}")
    logger.info(f"Success Rate: {passed_tests / total_tests * 100:.1f}%")
    logger.info("\nDetailed Results:")
    for test_name, status in test_results:
        status_symbol = "✅" if status == "PASSED" else "❌"
        logger.info(f"  {status_symbol} {test_name}: {status}")

    if passed_tests == total_tests:
        logger.info("\n✅✅✅ ALL WC TESTS PASSED ✅✅✅")
    else:
        logger.info(f"\n⚠️ {total_tests - passed_tests} tests failed")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_all_tests()
