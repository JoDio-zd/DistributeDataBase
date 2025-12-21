## 分布式事务系统

本项目实现了一个跨多 RM 的分布式事务系统，严格按需求文档的 2PC 流程与异常场景设计。组件分层清晰：Workflow Controller 作为客户端编排入口，Transaction Manager 负责 2PC 协调，多个 Resource Manager 负责本地数据与锁，全部通过 FastAPI 提供 HTTP 接口，底层用多实例 MySQL 持久化。

## 需求映射与设计对齐

- **两阶段提交完整实现**：TM 在 `src/tm/transaction_manager.py` 内实现 `/txn/start`、`/txn/commit`、`/txn/abort`，覆盖 prepare→commit 的全流程；RM 侧的 `prepare/commit/abort` 钩子位于 `src/rm/resource_manager.py`。
- **协调者职责明确**：WC（`src/wc/workflow_controller.py`）封装业务操作并调用 TM，TM 负责 enlist 管理与 2PC 协调，契合“协调层控制流程”的需求。
- **RM 可报告状态**：每个 RM 暴露 `/txn/prepare` 返回 ok/err，可被 TM 判定 prepared/冲突/dead；`/health` 用于活性探测。
- **故障与远程异常处理**：TM 在 prepare 失败或超时时广播 abort；commit/abort/prepare 具幂等语义，网络重放安全；`/shutdown`/`/die` 供测试模拟节点故障，重启后依赖 MySQL 数据目录持久化恢复。
- **并发冲突可诊断**：RM 内核采用 OCC + 行级锁，区分锁冲突、版本冲突、读写冲突等错误码，便于调用侧做重试/回退策略。

## 系统架构

Clients → Workflow Controller (WC) → Transaction Manager (TM) → Resource Managers (RM: flight/hotel/car/customer/reservation) → MySQL 分片

- WC：提供业务 API（增加资源、预订、查询），自动开启/提交/回滚事务。
- TM：全局 xid 分配，维护参与 RM 集合，执行 2PC。
- RM：本地事务 + 页缓存 + OCC 校验，FastAPI CRUD + 2PC 接口，数据落在独立 MySQL 实例。

## 两阶段提交与并发控制

1) **开始事务**：WC 调 TM `/txn/start` 获取 xid；RM 在每次写后调用 TM `/txn/enlist` 报名。
2) **Prepare（RM 侧）**：
   - 行级锁：`RowLockManager.try_lock` 逐 key 加锁，避免并发写冲突。
   - 版本/语义校验：`txn_start_xid` 记录读到的版本；prepare 比对当前 committed 版本，发现插入/删除/更新冲突返回 `ErrCode`。
   - 读写冲突检测：read-set 与最新版本比对，防止 read-write 冲突。
3) **Commit/Abort（TM 侧驱动）**：
   - TM 收齐所有 RM 的 prepare 结果，全成功才下发 commit，否则广播 abort。
   - RM commit 将影子记录合并入缓存并通过 `MySQLPageIO`/`MySQLMultiIndexPageIO` UPSERT 到 MySQL；abort 丢弃影子并解锁。
4) **幂等保障**：重复 prepare/commit/abort 均安全，满足网络重放与节点恢复场景。

## 存储设计亮点

- **页索引与分片**：`OrderedStringPageIndex` 采用前缀分片保持键空间有序；`DirectPageIndex` 支持固定宽度复合键，`LinearPageIndex` 支持整型分段。
- **页 IO**：`MySQLPageIO` 用范围查询拉页、批量 UPSERT 写回；`MySQLMultiIndexPageIO` 为复合主键拆分 delete/upsert，适配 `RESERVATIONS`。
- **缓存与影子记录**：`CommittedPagePool` 减少重复 page_in；`SimpleShadowRecordPool` 保存事务写集，实现写时复制。

## 异常与鲁棒性策略

- **节点宕机**：测试用 `/shutdown`/`/die` 可直接杀死 RM/TM 进程；数据目录挂载 `./data/mysql-*`，重启后 committed 数据仍在，满足 Durability。
- **远程异常/超时**：TM 对 prepare/commit/abort 调用设置 timeout；prepare 有失败即全局 abort，避免不一致。
- **锁冲突与回退**：prepare 在锁失败时立即释放已持有锁并返回 `LOCK_CONFLICT`；调用侧可重试。
- **测试验证**：`test/wc/test_level4_wc_rm.py` 演练 commit/abort 后崩溃重启场景；`test/rm`/`test/tm` 覆盖并发冲突、2PC 幂等、非法状态等。

## 业务域与表结构

初始化 SQL：`scripts/db-init/*/init.sql`

- `FLIGHTS(flightNum PK, price, numSeats, numAvail)`
- `HOTELS(location PK, price, numRooms, numAvail)`
- `CARS(location PK, price, numCars, numAvail)`
- `CUSTOMERS(custName PK)`
- `RESERVATIONS(custName, resvType, resvKey) PK(custName, resvType, resvKey)`（复合键宽度编码由 `DirectPageIndex` 处理）

## 快速开始

前置：Python 3.10+；Docker 可拉取 `mysql:oraclelinux9`；安装依赖 `pip install -e .`

1) 启动 MySQL 分片（数据持久化到 `./data`）：

```bash
python scripts/create_database.py
```

2) 启动服务（彩色前缀便于区分）：

```bash
python scripts/start_service.py up
# 仅 RM: python scripts/start_service.py rm
# 单个:  python scripts/start_service.py flight
```

3) 交互方式：
   - REST：TM `/txn/*`，RM `/records` + `/txn/*`，健康检查 `/health`。
   - SDK：使用 WC：

```python
from src.wc.workflow_controller import WC
wc = WC()
xid = wc.start()
wc.addFlight(xid, "0001", price=300, numSeats=5)
wc.addCustomer(xid, "alice")
wc.reserveFlight(xid, "alice", "0001")
wc.commit(xid)
```

## 快速验证

- RM 并发/OCC：`PYTHONPATH=. python test/rm/test_level1_flight_rm.py`
- TM + 单 RM 2PC：`PYTHONPATH=. python test/tm/test_level3_tm_rm.py`
- 全链路 + 崩溃恢复：`PYTHONPATH=. python test/wc/test_level4_wc_rm.py`

## 关键文件

- `src/tm/transaction_manager.py`：2PC 协调器。
- `src/rm/resource_manager.py`：OCC + 锁 + prepare/commit/abort 实现。
- `src/rm/impl/page_io/mysql_page_io.py` & `mysql_multi_index_page_io.py`：页入出与 MySQL 交互。
- `src/rm/impl/page_index/*`：页索引策略。
- `src/rms/service/*.py`：各 RM 的 FastAPI 入口与 enlist 逻辑。
- `src/wc/workflow_controller.py`：客户端侧编排与业务 API。
- `scripts/create_database.py`, `scripts/start_service.py`：环境与服务启动工具。
