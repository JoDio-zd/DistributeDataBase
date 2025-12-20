"""
Workflow Controller Test Helper Functions
提供 WC 测试的公共工具函数
"""
import threading
import time
import random
from src.wc.workflow_controller import WC
from test.wc.config import TestConfig


# ==================== WC Instance ====================

def new_wc():
    """创建新的 Workflow Controller 实例"""
    return WC()


# ==================== Setup Helpers ====================

def setup_flight(wc: WC, flight_num: str, price: int = None, seats: int = None):
    """Setup a flight for testing"""
    if price is None:
        price = TestConfig.DEFAULT_PRICE
    if seats is None:
        seats = TestConfig.DEFAULT_SEATS

    xid = wc.start()
    wc.addFlight(xid, flight_num, price, seats)
    wc.commit(xid)


def setup_hotel(wc: WC, location: str, price: int = None, rooms: int = None):
    """Setup a hotel for testing"""
    if price is None:
        price = TestConfig.DEFAULT_PRICE
    if rooms is None:
        rooms = TestConfig.DEFAULT_ROOMS

    xid = wc.start()
    wc.addHotel(xid, location, price, rooms)
    wc.commit(xid)


def setup_car(wc: WC, location: str, price: int = None, cars: int = None):
    """Setup a car rental location for testing"""
    if price is None:
        price = TestConfig.DEFAULT_PRICE
    if cars is None:
        cars = TestConfig.DEFAULT_CARS

    xid = wc.start()
    wc.addCar(xid, location, price, cars)
    wc.commit(xid)


def setup_customer(wc: WC, cust_id: str):
    """Setup a customer for testing"""
    xid = wc.start()
    wc.addCustomer(xid, cust_id)
    wc.commit(xid)


# ==================== Query Helpers ====================

def query_flight_avail(wc: WC, flight_num: str) -> int:
    """Query flight availability (returns numAvail or -1 if not found)"""
    xid = wc.start()
    flight = wc.queryFlight(xid, flight_num)
    wc.commit(xid)
    return flight["numAvail"] if flight else -1


def query_hotel_avail(wc: WC, location: str) -> int:
    """Query hotel availability (returns numAvail or -1 if not found)"""
    xid = wc.start()
    hotel = wc.queryHotel(xid, location)
    wc.commit(xid)
    return hotel["numAvail"] if hotel else -1


def query_car_avail(wc: WC, location: str) -> int:
    """Query car availability (returns numAvail or -1 if not found)"""
    xid = wc.start()
    car = wc.queryCar(xid, location)
    wc.commit(xid)
    return car["numAvail"] if car else -1


def query_customer_exists(wc: WC, cust_id: str) -> bool:
    """Check if customer exists"""
    xid = wc.start()
    cust = wc.queryCustomer(xid, cust_id)
    wc.commit(xid)
    return cust is not None


# ==================== Assertion Helpers ====================

def assert_flight_exists(wc: WC, flight_num: str, expected_avail: int = None):
    """Assert flight exists and optionally check availability"""
    avail = query_flight_avail(wc, flight_num)
    assert avail >= 0, f"Flight {flight_num} should exist"
    if expected_avail is not None:
        assert avail == expected_avail, f"Expected avail={expected_avail}, got {avail}"


def assert_flight_not_exists(wc: WC, flight_num: str):
    """Assert flight does not exist"""
    avail = query_flight_avail(wc, flight_num)
    assert avail == -1, f"Flight {flight_num} should not exist"


def assert_hotel_exists(wc: WC, location: str, expected_avail: int = None):
    """Assert hotel exists and optionally check availability"""
    avail = query_hotel_avail(wc, location)
    assert avail >= 0, f"Hotel {location} should exist"
    if expected_avail is not None:
        assert avail == expected_avail, f"Expected avail={expected_avail}, got {avail}"


def assert_hotel_not_exists(wc: WC, location: str):
    """Assert hotel does not exist"""
    avail = query_hotel_avail(wc, location)
    assert avail == -1, f"Hotel {location} should not exist"


def assert_car_exists(wc: WC, location: str, expected_avail: int = None):
    """Assert car location exists and optionally check availability"""
    avail = query_car_avail(wc, location)
    assert avail >= 0, f"Car {location} should exist"
    if expected_avail is not None:
        assert avail == expected_avail, f"Expected avail={expected_avail}, got {avail}"


def assert_car_not_exists(wc: WC, location: str):
    """Assert car location does not exist"""
    avail = query_car_avail(wc, location)
    assert avail == -1, f"Car {location} should not exist"


def assert_customer_exists(wc: WC, cust_id: str):
    """Assert customer exists"""
    exists = query_customer_exists(wc, cust_id)
    assert exists, f"Customer {cust_id} should exist"


def assert_customer_not_exists(wc: WC, cust_id: str):
    """Assert customer does not exist"""
    exists = query_customer_exists(wc, cust_id)
    assert not exists, f"Customer {cust_id} should not exist"


# ==================== Concurrency Helpers ====================

def tiny_sleep():
    """Random tiny sleep to simulate real-world timing jitter"""
    time.sleep(random.uniform(0, TestConfig.SLEEP_MAX))


def run_txn(wc: WC, txn_fn, results: list, start_barrier: threading.Barrier, worker_id: int = None):
    """
    Execute a transaction function with standard error handling

    txn_fn: function(wc, xid, worker_id) that performs transaction operations
    results: list to append result tuples: ('commit', xid) or ('abort', xid, reason)
    """
    xid = None
    try:
        start_barrier.wait()  # Synchronize start
        xid = wc.start()
        txn_fn(wc, xid, worker_id)
        wc.commit(xid)
        results.append(('commit', xid))
    except Exception as e:
        if xid is not None:
            try:
                wc.abort(xid)
            except:
                pass  # Ignore abort errors
        results.append(('abort', xid, str(e)))


def run_concurrent_txns(
    wc: WC,
    txn_fn,
    threads: int,
    rounds: int = 1,
    enable_metrics: bool = True
):
    """
    Run transactions concurrently for multiple rounds

    Args:
        wc: Workflow Controller instance
        txn_fn: Transaction function(wc, xid, worker_id)
        threads: Number of concurrent threads
        rounds: Number of rounds to run
        enable_metrics: Whether to print performance metrics

    Returns:
        dict with keys: 'total_commits', 'total_aborts', 'avg_throughput', 'round_results'
    """
    all_results = []

    for round_num in range(rounds):
        results = []
        barrier = threading.Barrier(threads)

        thread_list = [
            threading.Thread(target=run_txn, args=(wc, txn_fn, results, barrier, i))
            for i in range(threads)
        ]

        start_time = time.time()
        for t in thread_list:
            t.start()
        for t in thread_list:
            t.join()
        elapsed = time.time() - start_time

        commits = [r for r in results if r[0] == 'commit']
        aborts = [r for r in results if r[0] == 'abort']

        all_results.append({
            'round': round_num,
            'commits': len(commits),
            'aborts': len(aborts),
            'elapsed': elapsed,
        })

        # Print metrics every 50 rounds
        if enable_metrics and TestConfig.ENABLE_METRICS and (round_num + 1) % 50 == 0:
            success_rate = len(commits) / threads * 100 if threads > 0 else 0
            conflict_rate = len(aborts) / threads * 100 if threads > 0 else 0
            throughput = len(commits) / elapsed if elapsed > 0 else 0
            print(f"  Round {round_num + 1}/{rounds}:")
            print(f"    Success: {len(commits)}/{threads} ({success_rate:.1f}%)")
            print(f"    Conflict: {len(aborts)}/{threads} ({conflict_rate:.1f}%)")
            print(f"    Duration: {elapsed:.2f}s")
            print(f"    Throughput: {throughput:.1f} txn/s")

    # Aggregate stats
    total_commits = sum(r['commits'] for r in all_results)
    total_aborts = sum(r['aborts'] for r in all_results)
    total_elapsed = sum(r['elapsed'] for r in all_results)
    avg_throughput = total_commits / total_elapsed if total_elapsed > 0 else 0

    return {
        'total_commits': total_commits,
        'total_aborts': total_aborts,
        'avg_throughput': avg_throughput,
        'round_results': all_results,
    }


# ==================== Performance Metrics ====================

def print_final_metrics(test_name: str, stats: dict, threads: int, rounds: int):
    """Print final performance metrics for a test"""
    if not TestConfig.ENABLE_METRICS:
        return

    print(f"\n{'='*60}")
    print(f"Performance Metrics: {test_name}")
    print(f"{'='*60}")
    print(f"Configuration: {threads} threads × {rounds} rounds")
    print(f"Total Commits: {stats['total_commits']}")
    print(f"Total Aborts: {stats['total_aborts']}")
    print(f"Success Rate: {stats['total_commits'] / (threads * rounds) * 100:.2f}%")
    print(f"Average Throughput: {stats['avg_throughput']:.2f} txn/s")
    print(f"{'='*60}\n")
