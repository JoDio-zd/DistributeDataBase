"""
Workflow Controller Test Configuration
测试配置常量
"""


class TestConfig:
    """测试配置（已调整为快速测试模式）"""

    # 并发强度配置（降低以加快测试速度）
    THREADS_LOW = 5  # 低并发基准测试（从20降低）
    THREADS_MED = 10  # 中并发测试（从50降低）
    THREADS_HIGH = 15  # 高并发压力测试（从100降低）
    THREADS_ULTRA = 20  # 超高并发（从150降低）

    # 测试轮次（降低以加快测试速度）
    ROUNDS = 10  # 标准测试轮次（从200降低）
    ROUNDS_QUICK = 10  # 快速测试轮次（从50降低）

    # 并发控制
    SLEEP_MAX = 0.005  # 随机 sleep 上限（模拟真实延迟）

    # Test 数据前缀（确保测试隔离）
    FLIGHT_PREFIX = "FL"
    HOTEL_PREFIX = "HOT"
    CAR_PREFIX = "CAR"
    CUST_PREFIX = "CUST"
    RESV_PREFIX = "RSV"

    # 默认资源配置
    DEFAULT_PRICE = 500
    DEFAULT_SEATS = 10
    DEFAULT_ROOMS = 10
    DEFAULT_CARS = 10

    # 性能指标开关（用户要求）
    ENABLE_METRICS = True  # 输出冲突率、成功率、吞吐量等


class TestKeys:
    """测试用 key 常量（按类别组织）"""

    # Category 1: 唯一性约束类 (1xxx)
    UNIQUE_FLIGHT_BASE = "UF1"
    UNIQUE_HOTEL_BASE = "UH1"
    UNIQUE_CAR_BASE = "UC1"
    UNIQUE_CUST_BASE = "UCUST1"

    # Category 2: Abort 可见性类 (2xxx)
    ABORT_VISIBILITY_FLIGHT = "AF2001"
    ABORT_CROSS_SERVICE_FLIGHT = "AF2002"
    ABORT_CROSS_SERVICE_HOTEL = "AH2002"
    ABORT_CROSS_SERVICE_CUST = "ACUST2002"
    DELETE_ATOMICITY_FLIGHT = "AF2003"

    # Category 3: 不超卖类 (3xxx)
    RESERVE_FLIGHT_BASE = "RF3"
    RESERVE_HOTEL_BASE = "RH3"
    RESERVE_CAR_BASE = "RC3"
    RESERVE_CUST_BASE = "RCUST3"

    # Category 4: 跨服务事务类 (4xxx)
    CROSS_FLIGHT = "XF4001"
    CROSS_HOTEL = "XH4001"
    CROSS_CAR = "XC4001"
    COMPLEX_FLIGHT = "XF4002"
    COMPLEX_HOTEL = "XH4002"
    COMPLEX_CUST = "XCUST4002"

    # Category 5: 2PC 失败场景类 (5xxx)
    TPC_FAIL_FLIGHT = "TF5001"
    TPC_FAIL_HOTEL = "TH5001"
    TPC_MULTI_FLIGHT = "TF5002"
    TPC_MULTI_HOTEL = "TH5002"

    # Category 6: TM 状态管理类 (6xxx)
    # (使用数字 xid 而非 key string)

    # Category 7: 混合操作场景类 (7xxx)
    MIXED_FLIGHT_1 = "MF7001"
    MIXED_FLIGHT_2 = "MF7002"
    READ_OWN_WRITE_FLIGHT = "MF7003"
    READ_AFTER_DELETE_FLIGHT = "MF7004"

    # Category 8: 并发度与 key 分布类 (8xxx)
    HOTSPOT_FLIGHT = "HOTFL8001"
    UNIFORM_FLIGHT_BASE = "UFL8"
    MIXED_OPS_FLIGHT = "MOFL8003"

    # Category 9: 不超卖扩展（Priority 2）(9xxx)
    HOTEL_OVERSELL_TEST = "HOT9001"
    CAR_OVERSELL_TEST = "CAR9001"
