"""
RM Test Helper Functions
提供 Resource Manager 测试的公共工具函数
"""
import pymysql
from src.rm.base.err_code import ErrCode, RMResult
from src.rm.impl.page_index.order_string_page_index import OrderedStringPageIndex
from src.rm.impl.page_io.mysql_page_io import MySQLPageIO
from src.rm.resource_manager import ResourceManager


# ==================== Connection & RM Factory ====================

def new_conn():
    """创建新的数据库连接"""
    return pymysql.connect(
        host="127.0.0.1",
        port=33061,
        user="root",
        password="1234",
        database="rm_db",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def new_rm(
    conn, *, table: str, key_column: str, page_size: int = 2, key_width: int = 4
):
    """创建新的 Resource Manager 实例"""
    page_index = OrderedStringPageIndex(page_size, key_width)
    page_io = MySQLPageIO(
        conn=conn,
        table=table,
        key_column=key_column,
        page_index=page_index,
    )
    return ResourceManager(
        page_index=page_index,
        page_io=page_io,
        table=table,
        key_column=key_column,
        key_width=key_width,
    )


# ==================== Page & Record Management ====================

def preload_page_for_key(rm: ResourceManager, xid: int, key: str):
    """
    预加载 key 所在的 page 到 committed_pool

    IMPORTANT: RM 的 prepare() 要求 committed_pool 已经加载了 page
    最简单的方式是对该 key 调用一次 rm.read()（即使 key 不存在）
    """
    rm.read(xid, key)


def seed_if_absent(rm: ResourceManager, xid: int, record: dict, key_field: str):
    """
    如果记录不存在则插入 seed 数据，如果已存在则不做任何操作

    不依赖异常，只使用 RMResult 进行判断
    """
    key = record[key_field]
    # 预加载 page（seed 事务也需要）
    preload_page_for_key(rm, xid, key)

    # 如果已存在则跳过
    r = rm.read(xid, key)
    if r.ok:
        rm.abort(xid)  # 清理事务状态
        return

    # 插入并提交
    ins = rm.insert(xid, record)
    assert ins.ok, f"seed insert failed unexpectedly: {ins.err}"
    p = rm.prepare(xid)
    assert p.ok, f"seed prepare failed unexpectedly: {p.err}"
    rm.commit(xid)


def read_committed_like(rm: ResourceManager, key: str):
    """
    使用一个新的 xid 读取最终 committed 状态

    RM 允许不显式 start/commit 就读取，但仍会创建 txn_start_xid 条目
    """
    xid = 999999  # 使用大的 xid 避免与测试冲突
    r = rm.read(xid, key)
    assert r.ok, f"final read failed for key={key}: {r.err}"
    return r.value


def create_flight_record(flight_num: str, price: int = 500, seats: int = 100):
    """创建标准的 Flight 测试记录"""
    return {
        "flightNum": flight_num,
        "price": price,
        "numSeats": seats,
        "numAvail": seats,
    }


# ==================== Assertion Helpers ====================

def assert_rm_result_ok(result: RMResult, msg: str = ""):
    """断言 RMResult 成功"""
    assert result.ok, f"{msg} | Expected ok=True, got ok=False with err={result.err}"


def assert_rm_result_fail(result: RMResult, expected_err: ErrCode, msg: str = ""):
    """断言 RMResult 失败并且错误码匹配"""
    assert not result.ok, f"{msg} | Expected failure but got ok=True"
    assert result.err == expected_err, (
        f"{msg} | Expected err={expected_err}, got err={result.err}"
    )


def assert_key_not_found(result: RMResult, key: str = ""):
    """断言 KEY_NOT_FOUND 错误"""
    assert_rm_result_fail(
        result, ErrCode.KEY_NOT_FOUND, f"Expected KEY_NOT_FOUND for key={key}"
    )


def assert_key_exists(result: RMResult, key: str = ""):
    """断言 KEY_EXISTS 错误"""
    assert_rm_result_fail(
        result, ErrCode.KEY_EXISTS, f"Expected KEY_EXISTS for key={key}"
    )


def assert_version_conflict(result: RMResult, key: str = ""):
    """断言 VERSION_CONFLICT 错误"""
    assert_rm_result_fail(
        result, ErrCode.VERSION_CONFLICT, f"Expected VERSION_CONFLICT for key={key}"
    )


def assert_lock_conflict(result: RMResult, key: str = ""):
    """断言 LOCK_CONFLICT 错误"""
    assert_rm_result_fail(
        result, ErrCode.LOCK_CONFLICT, f"Expected LOCK_CONFLICT for key={key}"
    )


# ==================== Test Data Constants ====================

# Key 命名规范: {category_id}{test_num} (4位)
# Category 1xxx: WW Conflicts
# Category 2xxx: Lock Conflicts
# Category 3xxx: Multi-key Transactions
# Category 4xxx: Abort Tests
# Category 5xxx: Prepare Invariants
# Category 6xxx: Concurrency Stress
# Category 7xxx: Complex Scenarios

class TestKeys:
    """测试用 key 常量（确保每个测试用不同 key）"""

    # WW Conflicts (1xxx)
    WW_INSERT_INSERT = "1001"
    WW_INSERT_UPDATE = "1002"
    WW_INSERT_DELETE = "1003"
    WW_UPDATE_INSERT = "1004"
    WW_UPDATE_UPDATE = "1005"
    WW_UPDATE_DELETE = "1006"
    WW_DELETE_INSERT = "1007"
    WW_DELETE_UPDATE = "1008"
    WW_DELETE_DELETE = "1009"

    # Lock Conflicts (2xxx)
    LOCK_CONCURRENT_PREPARE = "2001"

    # Multi-key Transactions (3xxx)
    MULTI_KEY_1 = "3001"
    MULTI_KEY_2 = "3002"
    MULTI_KEY_3 = "3003"
    MULTI_KEY_4 = "3004"
    MULTI_NO_CONFLICT_1 = "3011"
    MULTI_NO_CONFLICT_2 = "3012"

    # Abort Tests (4xxx)
    ABORT_INSERT = "4001"
    ABORT_UPDATE = "4002"
    ABORT_DELETE = "4003"
    ABORT_LOCK_RELEASE = "4004"

    # Prepare Invariants (5xxx)
    PREPARE_WITHOUT_PRELOAD = "5001"
    READ_NONEXISTENT = "5002"
    UPDATE_NONEXISTENT = "5003"
    DELETE_NONEXISTENT = "5004"

    # Concurrency Stress (6xxx)
    STRESS_HOTSPOT = "6001"
    STRESS_UNIFORM_BASE = "6100"  # 6100-6199 for uniform distribution
    STRESS_SKEWED_BASE = "6200"   # 6200-6299 for skewed distribution

    # Complex Scenarios (7xxx)
    THREE_WAY_CONFLICT = "7001"
    READ_WRITE_READ = "7002"


class TestData:
    """测试数据常量"""
    DEFAULT_PRICE = 500
    DEFAULT_SEATS = 100
    DEFAULT_TABLE = "FLIGHTS"
    DEFAULT_KEY_COL = "flightNum"
    DEFAULT_PAGE_SIZE = 2
    DEFAULT_KEY_WIDTH = 4
