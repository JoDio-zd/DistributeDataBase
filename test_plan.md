# Test Suite Enhancement Plan - Distributed Database System

## Phase 1: Current Test Coverage Assessment

### A. test/rm/test.py - Resource Manager Tests

#### 当前覆盖范围 (Current Coverage)
1. **WW 冲突类 - Insert-Insert**: `test_ww_conflict_insert_insert_simulated()`
   - 测试两个事务并发插入同一 key
   - 验证 T2 prepare 失败，错误码 KEY_EXISTS

2. **WW 冲突类 - Update-Update**: `test_ww_conflict_update_update_simulated()`
   - 测试两个事务并发更新同一 key
   - 验证 T2 prepare 失败，错误码 VERSION_CONFLICT

3. **WW 冲突类 - Update-Delete**: `test_ww_conflict_update_delete_simulated()`
   - 测试 T1 update + T2 delete 同一 key
   - 验证 T2 prepare 失败，错误码 VERSION_CONFLICT

#### 当前问题与缺口 (Issues & Gaps)

**代码质量问题:**
1. **大量重复代码**: 每个测试都重复 conn/rm 创建、preload、seed 逻辑
2. **缺少公共框架**: 没有统一的测试基类或辅助函数集
3. **断言分散**: 断言逻辑散落在测试中，不利于维护
4. **日志缺失**: 测试失败时难以定位问题

**功能覆盖缺口:**
1. **缺少实际并发测试**: 当前都是"模拟并发"（sequential execution），没有真正的多线程冲突
2. **WW 冲突场景不全**:
   - 缺少 delete-delete
   - 缺少 delete-insert
   - 缺少 insert-update
3. **缺少 WR 冲突测试**: 虽然 RM 使用 OCC 不跟踪 read set，但应测试"读到旧版本"是否符合预期
4. **缺少锁冲突测试**: prepare 阶段的 LOCK_CONFLICT 错误码未覆盖
5. **缺少多 key 事务**: 只测试单 key 操作，未测试一个事务修改多个 key 的场景
6. **缺少 page 边界测试**: 未测试同一 page 内多 key vs 跨 page 的行为差异
7. **缺少 abort 路径验证**: 只测试 commit 路径，未验证 abort 后状态回滚
8. **缺少 prepare 不变式测试**: 未测试 prepare 前未 preload page 的失败场景（INTERNAL_INVARIANT）
9. **缺少错误码覆盖**: 15+ 种错误码中只测试了 3 种
10. **缺少压力测试**: 无高并发、多轮迭代的负载测试

**可维护性问题:**
1. 测试用例名称不够描述性
2. 缺少中文注释说明测试意图
3. 测试组织松散，未按类别分组

### B. test/wc/test.py - Workflow Controller Tests

#### 当前覆盖范围 (Current Coverage)
1. **唯一性约束类**: `case_concurrent_addFlight()` ✅ 已启用
   - 测试多个事务并发 addHotel（代码中实际测的是 Hotel，不是 Flight）
   - 验证最多 1 个事务 commit

2. **Abort 可见性类**: `case_abort_visibility()` ❌ 已注释
3. **不超卖类**: `case_concurrent_reserve()` ❌ 已注释
4. **删除原子性类**: `case_delete_atomicity()` ❌ 已注释

#### 当前问题与缺口 (Issues & Gaps)

**严重问题:**
1. **大部分测试被注释掉**: 只有 1/4 测试在运行
2. **Bug**: `case_concurrent_addFlight` 中调用 `wc.addHotel` 而非 `wc.addFlight`

**功能覆盖缺口:**
1. **缺少跨服务事务**: 未测试一个事务中同时操作 flight + hotel + customer + reservation
2. **缺少 2PC 失败场景**:
   - prepare 在某个 RM 失败，验证 TM 是否 abort 所有 RM
   - commit 阶段网络故障（虽然 _safe_commit 会吞掉异常，但应验证）
3. **缺少 TM 状态管理测试**:
   - 重复 commit/abort 同一 xid
   - 使用不存在的 xid
   - enlist 后 TM 是否正确追踪 RM 列表
4. **缺少混合场景**:
   - 同时有成功和失败的事务
   - 多种操作类型混合（add + delete + reserve + query）
5. **缺少热点 key 测试**: 所有并发操作都打在同一个 key 上（最大冲突）
6. **缺少均匀分布 key 测试**: 并发操作打在不同 key 上（最小冲突）
7. **缺少长事务链测试**: T1 → T2 → T3 交错执行的复杂场景
8. **缺少 reserveFlight 逻辑测试**:
   - Customer 不存在
   - Flight 不存在
   - numAvail 不足
   - 多步骤操作的事务性（query + update + insert）
9. **缺少并发度调优**: THREADS=8 可能不够高，未测试高并发下的表现

**可维护性问题:**
1. 测试函数命名不一致（case_ vs test_）
2. 缺少测试类别注释
3. 错误信息不够详细（如 results 内容未打印）
4. 测试配置硬编码（THREADS, ROUNDS, FLIGHT, PRICE 等）

---

## Phase 2: Source Code Analysis Summary

### RM Concurrency Control Mechanism

**Pessimistic Locking (Prepare Phase)**
- `RowLockManager.try_lock()` 在 prepare 阶段按 sorted key order 获取锁
- 失败返回 LOCK_CONFLICT，释放已获取的锁
- Commit/Abort 时释放所有锁

**Optimistic Concurrency Control (Prepare Phase)**
- 版本号机制: 每个 record 有 `version` 字段
- 事务首次访问 key 时记录 `txn_start_xid[xid][key] = record.version`
- Prepare 时验证: `committed_record.version == start_version`
- 失败返回 VERSION_CONFLICT

**关键发现:**
1. RM 不跟踪 read set，只跟踪 write set (shadow records)
2. Prepare 成功后，commit **必然成功**（这是 2PC 的核心约束）
3. 系统无崩溃恢复逻辑
4. 系统无自动重试逻辑
5. 锁只在 prepare-commit/abort 期间持有，write phase 不持锁

### TM 2PC Implementation

**Phase 1 - Prepare:**
```python
for rm in txn.rms:
    resp = requests.post(f"{rm}/txn/prepare", json={"xid": xid})
    if not resp.json().get("ok", False):
        # Any failure → abort all
        for r in txn.rms:
            _safe_abort(r, xid)
        return {"ok": False}
```

**Phase 2 - Commit:**
```python
for rm in txn.rms:
    _safe_commit(rm, xid)  # Swallows exceptions
txn.state = "COMMITTED"
```

**关键发现:**
1. All-or-nothing: 任一 RM prepare 失败 → 全部 abort
2. Commit phase 不检查返回值（_safe_commit 吞异常）
3. TM 维护事务状态: ACTIVE → COMMITTED/ABORTED
4. 无持久化，重启后状态丢失

---

## Phase 3: Detailed Test Enhancement Plan

### 3.1 test/rm/test.py Enhancement Plan

#### 【测试基础设施重构】

**Step 1: 创建测试基类与工具函数**
- `RMTestBase` 类:
  - `setUp()`: 初始化 conn, rm
  - `tearDown()`: 关闭连接
  - `seed_record()`: 统一的记录预设方法
  - `verify_committed()`: 统一的最终状态验证
  - `assert_rm_result()`: 统一的 RMResult 断言

- 工具函数模块 `test/rm/helpers.py`:
  - `preload_page_for_key()` (保留现有)
  - `seed_if_absent()` (保留并增强)
  - `read_committed_like()` (保留并增强)
  - `create_test_record()`: 生成测试数据
  - `assert_error_code()`: 错误码断言

**Step 2: 测试数据管理**
- 定义测试数据常量（FLIGHT_KEYS, PRICES, etc.）
- **数据隔离策略**: 每个测试用唯一 key（例如: test_ww_insert_insert 用 "1001", test_ww_update_update 用 "1002"）
- 无需清理 DB，测试可并行运行
- Key 命名规范: "{test_category_id}{test_number}" (4 位，补零)

#### 【新增测试类别】

**Category 1: WW 冲突类 - 完整场景矩阵**

测试用例矩阵:
| T1 操作 | T2 操作 | 期望结果 | 错误码 | 测试函数名 |
|---------|---------|----------|--------|-----------|
| Insert | Insert | T2 prepare 失败 | KEY_EXISTS | test_ww_conflict_insert_insert ✅ 已有 |
| Insert | Update | T2 prepare 失败 | KEY_NOT_FOUND | test_ww_conflict_insert_update_NEW |
| Insert | Delete | T2 prepare 失败 | KEY_NOT_FOUND | test_ww_conflict_insert_delete_NEW |
| Update | Insert | T1 commit 后 key 存在 | N/A | test_ww_conflict_update_insert_NEW |
| Update | Update | T2 prepare 失败 | VERSION_CONFLICT | test_ww_conflict_update_update ✅ 已有 |
| Update | Delete | T2 prepare 失败 | VERSION_CONFLICT | test_ww_conflict_update_delete ✅ 已有 |
| Delete | Insert | T2 commit 成功 | N/A | test_ww_conflict_delete_insert_NEW |
| Delete | Update | T2 prepare 失败 | VERSION_CONFLICT | test_ww_conflict_delete_update_NEW |
| Delete | Delete | T2 prepare 失败 | VERSION_CONFLICT or KEY_NOT_FOUND | test_ww_conflict_delete_delete_NEW |

每个测试需验证:
1. 操作是否返回正确结果（ok/not ok）
2. 错误码是否正确
3. 最终 committed 状态是否符合预期（只有 T1 的修改可见）

**Category 2: 锁冲突类 (LOCK_CONFLICT)**

难点: RowLockManager 的锁只在 prepare 阶段持有，且是同步的（try_lock 立即返回）。
要触发 LOCK_CONFLICT，需要:
- 方案 A: 修改 RowLockManager 为异步获锁（不在本次范围）
- 方案 B: 通过 mock 或并发控制模拟锁占用状态
- **推荐方案**: 使用真实并发场景：T1 在 prepare 中，T2 同时 prepare

测试用例:
- `test_lock_conflict_concurrent_prepare()`: 两个事务同时 prepare 同一 key
  - 使用 threading.Barrier 同步
  - 验证至少一个事务拿到锁，另一个返回 LOCK_CONFLICT 或成功（取决于时序）
  - 或者验证最终只有一个 commit 成功

**Category 3: 多 key 事务类**

- `test_multi_key_same_page()`: 同一 page 内多个 key
  - T1 修改 key1, key2（同一 page）
  - T2 修改 key1
  - 验证 T2 prepare 失败（key1 冲突）
  - 验证 T1 commit 后两个 key 都生效

- `test_multi_key_cross_page()`: 跨 page 多个 key
  - page_size=2, T1 修改 key1 (page 0), key3 (page 1)
  - T2 修改 key1
  - 验证 T2 prepare 失败
  - 验证锁按 sorted order 获取（避免死锁）

- `test_multi_key_no_conflict()`: 不同 key 无冲突
  - T1 修改 key1, T2 修改 key2
  - 两者都应该 commit 成功

**Category 4: Abort 路径验证类**

- `test_abort_rollback_insert()`:
  - T1 insert key1, abort
  - T2 read key1 → KEY_NOT_FOUND

- `test_abort_rollback_update()`:
  - Seed key1=100
  - T1 update key1=200, abort
  - T2 read key1 → 仍为 100

- `test_abort_rollback_delete()`:
  - Seed key1
  - T1 delete key1, abort
  - T2 read key1 → 仍存在

- `test_abort_releases_locks()`:
  - T1 update key1, prepare (持有锁), abort
  - T2 update key1, prepare → 应该成功（锁已释放）

**Category 5: Prepare 不变式与内部错误类**

- `test_prepare_without_preload()`:
  - 不调用 preload_page_for_key
  - 直接 insert + prepare
  - 验证是否返回 INTERNAL_INVARIANT（根据源码 line 185）

- `test_read_nonexistent_key()`:
  - read 不存在的 key
  - 验证返回 KEY_NOT_FOUND

- `test_update_nonexistent_key()`:
  - update 不存在的 key
  - 验证返回 KEY_NOT_FOUND（根据源码 line 142）

- `test_delete_nonexistent_key()`:
  - delete 不存在的 key
  - 验证返回 KEY_NOT_FOUND

- `test_duplicate_prepare()`:
  - 同一 xid 调用两次 prepare
  - 验证行为（源码中无显式检查，应测试实际行为）

**Category 6: 并发压力测试类**

- `test_concurrent_inserts_stress()`:
  - N 个线程（N=50）并发插入同一 key
  - 验证最多 1 个成功
  - 运行 M 轮（M=100）

- `test_concurrent_updates_stress()`:
  - Seed key1
  - N 个线程并发 update key1
  - 验证最多 1 个成功，最终值为该线程的值

- `test_hotspot_key_contention()`:
  - 所有并发操作都打在 key="0001"
  - 测量冲突率、成功率

- `test_uniform_key_distribution()`:
  - N 个线程操作 N 个不同 key
  - 验证所有事务都成功（无冲突）
  - 测量吞吐量

- `test_skewed_key_distribution()`:
  - 80% 操作打在 20% 的 key 上（Zipf 分布）
  - 验证冲突率符合预期

**Category 7: 复杂交错场景类**

- `test_three_way_conflict()`:
  - T1, T2, T3 都读 key1（version=0）
  - T1 commit (version=1)
  - T2 prepare → VERSION_CONFLICT
  - T3 prepare → VERSION_CONFLICT

- `test_read_write_read_chain()`:
  - T1 read key1=100
  - T1 update key1=200
  - T1 read key1 → 应该读到 200（自己的 shadow）
  - T1 commit
  - T2 read key1 → 应该读到 200

**Category 8: Page Index 与边界测试类**

- `test_page_boundary_insert()`:
  - page_size=2
  - Insert key1, key2 → page 0
  - Insert key3 → page 1
  - 验证 page_index 正确路由

- `test_page_overflow_handling()`:
  - 插入大量 key 导致多个 page
  - 验证 page_in/page_out 正确性

#### 【测试组织结构】

```python
# test/rm/test.py

# ==================== 测试基础设施 ====================
class RMTestBase:
    ...

# ==================== 测试类别 1: WW 冲突类 ====================
class TestWWConflicts(RMTestBase):
    """【测试分类】Write-Write 冲突检测
    【测试目标】验证 OCC 版本检测与语义冲突检测
    """

    def test_ww_conflict_insert_insert(self):
        """【场景】两事务并发插入同一 key
        【期望】T2 prepare 失败，错误码 KEY_EXISTS"""
        ...

    def test_ww_conflict_update_update(self):
        ...

# ==================== 测试类别 2: 锁冲突类 ====================
class TestLockConflicts(RMTestBase):
    ...

# ==================== 测试类别 3: 多 key 事务类 ====================
class TestMultiKeyTransactions(RMTestBase):
    ...

# ... 其他类别 ...
```

---

### 3.2 test/wc/test.py Enhancement Plan

#### 【测试基础设施重构】

**Step 1: 测试配置与工具类**

```python
# test/wc/config.py
class TestConfig:
    # 用户指定: 高强度并发配置
    THREADS_LOW = 10      # 低并发基准
    THREADS_MED = 50      # 中并发
    THREADS_HIGH = 100    # 高并发（用户要求）
    ROUNDS = 200          # 多轮迭代
    SLEEP_MAX = 0.005

    # Test data
    FLIGHT_BASE = "FL"
    HOTEL_BASE = "HOT"
    CAR_BASE = "CAR"
    CUST_BASE = "CUST"

    PRICE = 500
    SEATS = 10

    # 用户要求: 性能指标开关
    ENABLE_METRICS = True  # 输出冲突率、成功率等

# test/wc/helpers.py
def setup_flight(wc, flight_num, seats=10):
    """Setup a flight for testing"""
    xid = wc.start()
    wc.addFlight(xid, flight_num, 500, seats)
    wc.commit(xid)

def verify_flight_avail(wc, flight_num, expected_avail):
    """Verify flight availability"""
    xid = wc.start()
    flight = wc.queryFlight(xid, flight_num)
    wc.commit(xid)
    assert flight["numAvail"] == expected_avail

def run_concurrent_txns(wc, txn_fn, threads, rounds=1):
    """Run transactions concurrently and return results"""
    ...
```

**Step 2: 修复现有测试**
1. 修复 `case_concurrent_addFlight` 中的 bug（addHotel → addFlight）
2. 取消注释其他测试并修复
3. 统一测试函数命名（case_ → test_）

#### 【新增测试类别】

**Category 1: 唯一性约束类（扩展）**

- `test_concurrent_addFlight_stress()`: ✅ 修复现有
  - 修正为 addFlight
  - 增加验证：查询 flight 确认只有 1 个存在

- `test_concurrent_addHotel()`:
  - 同上，测试 Hotel 唯一性

- `test_concurrent_addCar()`:
  - 同上，测试 Car 唯一性

- `test_concurrent_addCustomer()`:
  - 同上，测试 Customer 唯一性

**Category 2: Abort 可见性与原子性类**

- `test_abort_visibility()`: ✅ 恢复现有
  - 验证 abort 的修改不可见

- `test_delete_atomicity()`: ✅ 恢复现有
  - 验证 delete abort → 记录仍存在
  - 验证 delete commit → 记录消失

- `test_cross_service_abort()`:
  - T1: addFlight + addHotel + addCustomer, abort
  - 验证所有服务都回滚（查询都返回 None）

- `test_partial_operation_abort()`:
  - T1: addFlight (成功), reserveFlight (失败), abort
  - 验证 flight 未创建

**Category 3: 不超卖类（扩展）**

- `test_concurrent_reserve_no_oversell()`: ✅ 恢复现有
  - 验证 reserveFlight 不超卖
  - 增加验证：检查 reservation 记录数 ≤ SEATS

- `test_reserve_customer_not_exist()`:
  - reserveFlight 时 customer 不存在
  - 验证事务失败（RuntimeError）

- `test_reserve_flight_not_exist()`:
  - reserveFlight 时 flight 不存在
  - 验证事务失败

- `test_reserve_insufficient_seats()`:
  - flight 只剩 2 个座位
  - T1 预订 3 个 → 失败
  - T2 预订 2 个 → 成功

- `test_reserve_hotel_no_oversell()`:
  - 同 reserveFlight，测试 hotel

- `test_reserve_car_no_oversell()`:
  - 同 reserveFlight，测试 car

**Category 4: 跨服务事务类（2PC 核心）**

- `test_cross_service_commit()`:
  - T1: addFlight + addHotel + addCar
  - 验证所有服务都 commit（查询都返回记录）
  - 验证 TM 正确 enlist 了 3 个 RM

- `test_cross_service_complex_workflow()`:
  - Setup: addFlight, addHotel, addCustomer (3 个独立事务)
  - T1: reserveFlight + reserveHotel (同一客户, 同一事务)
  - 验证两个 reservation 都创建
  - 验证 flight.numAvail 和 hotel.numAvail 都减少

- `test_cross_service_one_fails()`:
  - Setup: addFlight, addCustomer (无 Hotel)
  - T1: reserveFlight + reserveHotel (hotel 不存在 → 失败)
  - T1 因异常调用 abort
  - 验证 flight.numAvail 未减少（rollback）

**Category 5: 2PC 失败场景类**

- `test_prepare_fails_on_one_rm()`:
  - Setup: seed flight with key="0001"
  - T1: update flight "0001"
  - T2: update flight "0001"
  - T1 commit (成功)
  - T2 commit (prepare 失败 → TM abort all)
  - 验证 T2 返回 ok=False
  - 验证最终值为 T1 的值

- `test_prepare_fails_multiple_rms()`:
  - Setup: seed flight "0001", hotel "0001"
  - T1: update flight + update hotel
  - T2: update flight + update hotel
  - T1 commit
  - T2 commit → flight prepare 失败 → TM abort hotel 也 abort
  - 验证两个服务都是 T1 的值

- `test_tm_enlist_idempotent()`:
  - T1: addFlight (enlist flight RM)
  - T1: addFlight 另一个航班 (再次 enlist)
  - 验证 TM 的 txn.rms 只有 1 个 flight RM URL

**Category 6: TM 状态管理类**

- `test_commit_nonexistent_xid()`:
  - 调用 commit(xid=99999) (不存在)
  - 验证返回 404 错误

- `test_abort_nonexistent_xid()`:
  - 调用 abort(xid=99999)
  - 验证返回 404 错误

- `test_double_commit()`:
  - T1: addFlight, commit
  - 再次 commit(T1)
  - 验证返回 409 错误 (transaction already COMMITTED)

- `test_commit_after_abort()`:
  - T1: addFlight, abort
  - 尝试 commit(T1)
  - 验证返回 409 错误

- `test_abort_idempotent()`:
  - T1: addFlight, abort
  - 再次 abort(T1)
  - 验证返回 ok=True（幂等）

**Category 7: 混合操作场景类**

- `test_mixed_add_delete_query()`:
  - Setup: addFlight "FL01"
  - T1: deleteFlight "FL01" + addFlight "FL02"
  - 验证 FL01 消失，FL02 存在

- `test_read_own_write()`:
  - T1: addFlight "FL01"
  - T1: queryFlight "FL01" (在 commit 前)
  - 验证能读到（事务内可见）

- `test_read_after_delete()`:
  - Setup: addFlight "FL01"
  - T1: deleteFlight "FL01"
  - T1: queryFlight "FL01"
  - 验证返回 None（事务内已删除）

**Category 8: 并发度与 key 分布类**

- `test_hotspot_key_high_concurrency()`:
  - THREADS=50, 所有线程 addFlight "HOTKEY"
  - 验证只有 1 个成功
  - 统计成功率 = 1/50 = 2%

- `test_uniform_key_low_conflict()`:
  - THREADS=50, 每个线程 addFlight "FL{i}" (不同 key)
  - 验证所有 50 个都成功
  - 成功率 = 100%

- `test_mixed_operations_high_concurrency()`:
  - Setup: addFlight "FL01" (seats=50)
  - THREADS=100, 每个线程 reserveFlight "FL01" (1 seat)
  - 验证最多 50 个成功
  - 验证 numAvail = 0

**Category 9: 长事务链与复杂交错类**

- `test_long_transaction_chain()`:
  - T1: addFlight "FL01"
  - T2: (wait for T1 commit) queryFlight "FL01" → updateFlight price
  - T3: (wait for T2 commit) reserveFlight "FL01"
  - 验证链式依赖正确执行

- `test_three_way_interleave()`:
  - Setup: addFlight "FL01" (seats=3)
  - T1, T2, T3 同时 reserveFlight "FL01" (1 seat each)
  - 使用 Barrier 同步启动
  - 验证正好 3 个成功

#### 【测试组织结构】

```python
# test/wc/test.py

# ==================== 测试配置 ====================
from test.wc.config import TestConfig
from test.wc.helpers import *

# ==================== 测试类别 1: 唯一性约束类 ====================
class TestUniquenessConstraints:
    """【测试分类】唯一性约束
    【测试目标】验证并发插入同一 key 时只有一个成功
    """

    def test_concurrent_addFlight_stress(self):
        ...

# ==================== 测试类别 2: Abort 可见性与原子性类 ====================
class TestAbortVisibility:
    ...

# ... 其他类别 ...
```

---

## Phase 4: Implementation Priorities & Configuration

### 用户确认的实现范围: Priority 1 + Priority 2 全部实现

### 配置参数（用户指定）:
- **数据隔离策略**: 使用不同 key（test1 用 "0001", test2 用 "0002" 等）
- **并发强度**: THREADS=50-100, ROUNDS=200+（高强度压力测试）
- **性能指标**: 必须输出冲突率、成功率、吞吐量等统计信息

### Priority 1 (Must Have) - 基础覆盖补全

**test/rm/test.py:**
1. 补全 WW 冲突矩阵（6 个新测试）
2. Abort 路径验证（4 个测试）
3. 多 key 事务基本场景（3 个测试）

**test/wc/test.py:**
1. 修复并恢复现有 4 个测试
2. 跨服务事务基本场景（2 个测试）
3. 2PC 失败场景（2 个测试）

### Priority 2 (Should Have) - 并发与压力 ✅ 本次实现

**test/rm/test.py:**
1. 并发压力测试（热点 key, 均匀分布）- THREADS=100
2. 锁冲突测试（真实并发场景）

**test/wc/test.py:**
1. 不超卖扩展测试（hotel, car）- THREADS=80
2. 高并发混合操作 - THREADS=100

### Priority 3 (Nice to Have) - 延后

**test/rm/test.py:**
1. Page 边界测试（可选）
2. 复杂交错场景（可选）

**test/wc/test.py:**
1. TM 状态管理完整覆盖（可选）
2. 长事务链（可选）

---

## Phase 5: Quality Standards

### 每个测试必须包含:

1. **清晰的中文注释**:
   ```python
   def test_ww_conflict_insert_insert(self):
       """【测试分类】WW 冲突类
       【测试场景】两个事务并发插入同一 key
       【期望结果】T1 commit 成功，T2 prepare 失败
       【错误码】KEY_EXISTS
       【覆盖的源码路径】src/rm/resource_manager.py:197
       """
   ```

2. **详细的断言与错误信息**:
   ```python
   assert not p2.ok, f"T2 prepare should fail, but got ok=True"
   assert p2.err == ErrCode.KEY_EXISTS, f"Expected KEY_EXISTS, got {p2.err}"
   ```

3. **可复现的测试数据**:
   - 使用固定的 key 值（便于调试）
   - 或使用随机 key + 日志输出（压力测试）

4. **测试隔离**:
   - 每个测试使用独立的 key
   - 或在测试前清理 DB

5. **性能指标（压力测试 - 用户要求）**:
   ```python
   # 必须输出的指标
   print(f"✅ Hotspot test: {success_count}/{THREADS} succeeded")
   print(f"   Success rate: {success_count / THREADS * 100:.1f}%")
   print(f"   Conflict rate: {(THREADS - success_count) / THREADS * 100:.1f}%")
   print(f"   Duration: {elapsed_time:.2f}s")
   print(f"   Throughput: {success_count / elapsed_time:.1f} txn/s")
   ```

### 禁止事项:

1. ❌ 不得删除现有测试
2. ❌ 不得弱化现有测试的断言
3. ❌ 不得假设系统有 scan/range query 能力
4. ❌ 不得假设系统有崩溃恢复能力（除非未来实现）
5. ❌ 不得假设 prepare 后 commit 可能失败（违反 2PC 约束）

---

## Phase 6: Execution Steps

### Step 1: 评估输出 (本阶段)
- 输出当前测试覆盖评估（上述 Phase 1）
- 输出测试改造 Plan（上述 Phase 2-5）

### Step 2: test/rm/test.py 重构
1. 创建 `test/rm/helpers.py` 和 `RMTestBase`
2. 重构现有 3 个测试到新框架
3. 运行并验证现有测试仍然通过

### Step 3: test/rm/test.py 扩展 (Priority 1)
1. 实现 WW 冲突矩阵新测试
2. 实现 Abort 路径验证
3. 实现多 key 事务测试
4. 运行全部测试

### Step 4: test/wc/test.py 修复与重构
1. 修复 `case_concurrent_addFlight` bug
2. 恢复其他 3 个注释的测试
3. 创建 `test/wc/config.py` 和 `test/wc/helpers.py`
4. 统一测试结构

### Step 5: test/wc/test.py 扩展 (Priority 1)
1. 实现跨服务事务测试
2. 实现 2PC 失败场景测试
3. 运行全部测试

### Step 6: Priority 2 & 3 测试
- 按优先级依次实现
- 每个 Priority 完成后运行全量测试

### Step 7: 文档与总结
- 更新测试 README
- 输出测试覆盖率报告
- 记录已知限制（如无崩溃恢复测试）

---

## Critical Files to Modify

### 必改文件:
1. `/Users/kevintu/sources/pythonProjects/Fudan code/DistributeDataBase/test/rm/test.py`
2. `/Users/kevintu/sources/pythonProjects/Fudan code/DistributeDataBase/test/wc/test.py`

### 新增文件:
1. `/Users/kevintu/sources/pythonProjects/Fudan code/DistributeDataBase/test/rm/helpers.py`
2. `/Users/kevintu/sources/pythonProjects/Fudan code/DistributeDataBase/test/wc/config.py`
3. `/Users/kevintu/sources/pythonProjects/Fudan code/DistributeDataBase/test/wc/helpers.py`

### 参考文件（只读）:
- `/Users/kevintu/sources/pythonProjects/Fudan code/DistributeDataBase/src/rm/resource_manager.py`
- `/Users/kevintu/sources/pythonProjects/Fudan code/DistributeDataBase/src/rm/base/err_code.py`
- `/Users/kevintu/sources/pythonProjects/Fudan code/DistributeDataBase/src/tm/transaction_manager.py`
- `/Users/kevintu/sources/pythonProjects/Fudan code/DistributeDataBase/src/wc/workflow_controller.py`
