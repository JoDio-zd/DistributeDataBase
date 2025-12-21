# 分布式旅游预订系统 (课程项目)

本项目实现了一个分布式旅游预订系统，完全符合构建 Client-WC-TM-RM 栈并提供 ACID 保证的课程要求。设计重点在于显式的事务控制、独立于数据库的内存并发管理，以及抗崩溃的持久化机制，使得 PDF 中的每项要求都能直接映射到本项目的具体组件中。

## 架构

* **客户端 / 工作流控制器 (WC)**：`src/wc/workflow_controller.py` 提供了一个 Python 客户端外观（Facade）。它隐藏了 TM/RM 的细节，串联起跨 RM 的业务逻辑（如库存检查 + 预订写入），并暴露简单的接口如 `start`、`commit`、`reserveFlight` 等。
* **事务管理器 (TM)**：`src/tm/transaction_manager.py` 运行在 9001 端口的 FastAPI 服务，提供 `/txn/start|commit|abort|enlist` 接口。它负责协调所有注册 RM 的两阶段提交（2PC），并重试提交调用以应对瞬时故障。
* **资源管理器 (RM)**：每个数据集对应一个 FastAPI 服务 —— 航班 `8001`、酒店 `8002`、汽车 `8003`、客户 `8004`、预订 `8005`。每个 RM 拥有一张不相交的表（无副本），持久化到各自的 MySQL 实例，并暴露 CRUD 和 2PC 接口。
* **存储后端**：通过 `scripts/create_database.py` 启动的 MySQL 容器（每个 RM 一个，客户/预订共用一个 DB）。不依赖数据库锁 —— 仅使用我们自定义的内存锁管理器来保证正确性。

## 数据模型

* **FLIGHTS** (flightNum, price, numSeats, numAvail)
* **HOTELS** (location, price, numRooms, numAvail)
* **CARS** (location, price, numCars, numAvail)
* **CUSTOMERS** (custName)
* **RESERVATIONS** (custName, resvType, resvKey) 在预订 RM 中使用编码的复合主键 (`cust|type|key`)。

## 设计与需求映射

* **两阶段提交 (TM <-> RM)**：TM 驱动各个已注册 RM 的 prepare/commit/abort 流程；RM 实现 `/txn/prepare|commit|abort` 并在确认前持久化 prepare 状态，确保在崩溃后仍能完成提交。
* **不依赖数据库的严格锁定**：`RowLockManager` 在 prepare 阶段授予基于 Key 的锁并持有至 commit/abort。读/写操作维护版本化的读写集（Read/Write Sets）以检测 RW/WW 冲突；完全不依赖 MySQL 的锁机制。
* **用于原子性/持久化的影子分页 (Shadow Paging)**：每个 RM 使用 `SimpleShadowRecordPool` 维护修改记录的私有副本（影子页）。在提交时，`CommittedPagePool` 中的页面被更新并通过 `PageIO` 刷入磁盘。处于 Prepared 状态的影子副本会持久化到 `rm_txn_state/<table>_rm_state.json` 中，通过原子文件替换实现。
* **崩溃恢复**：RM 构造函数会调用 `recover()` 加载已处于 Prepared 状态的事务，重建影子记录并重新获取锁，以便 TM 安全地完成最终决策。TM 提供 `/die` 接口用于故障注入；提交调用会进行重试以容忍短时间停机。
* **清晰的分区**：每种资源类型对应一个 RM，符合“无副本、特定类别的 RM”要求；WC 将每个业务动作路由到对应的 RM，同时验证可用性和客户存在性。

## 快速入门

**前提条件**：Python 3.10+，Docker，以及 `uvicorn`（通过项目依赖安装）。请在仓库根目录下运行以下步骤。

1. **安装依赖**

```bash
pip install -e .
```

2. **启动 MySQL 集群** (每个 RM 一个容器)

```bash
python scripts/create_database.py
```

端口：航班 `33061`，酒店 `33062`，汽车 `33063`，客户/预订 `33064`。数据目录位于 `./data/mysql-*`。

3. **启动所有服务** (TM + 所有 RM)

```bash
python scripts/start_service.py up
```

你也可以启动子集，例如 `python scripts/start_service.py tm` 或 `python scripts/start_service.py rm`（启动所有 RM 但不启动 TM）。

## 示例流程 (Python)

```python
from src.wc.workflow_controller import WC

wc = WC()
xid = wc.start()

wc.addCustomer(xid, "alice")
wc.addFlight(xid, "001", price=500, numSeats=3)
wc.reserveFlight(xid, "alice", "001")  # 检查客户 + 可用性，然后写入航班 RM 和预订 RM

wc.commit(xid)
```

如果任何步骤失败，调用 `wc.abort(xid)` 即可回滚。

## 运维说明

* **健康检查**：每个服务都暴露 `/health`；RM 还提供 `/shutdown` 用于快速关闭，TM 提供 `/die` 用于崩溃测试。
* **日志**：RM 服务默认以 DEBUG 级别记录日志，以显示锁定、准备（prepare）和版本控制决策。
* **恢复文件**：Prepared 事务的快照存储在 `rm_txn_state/` 下；一旦 commit/abort 完成，这些文件会被清除。

## 仓库布局

* `src/tm/`：事务管理器服务。
* `src/wc/`：工作流控制器客户端。
* `src/rm/`：存储/并发原语（页面缓存、锁管理器、影子页、页面 I/O）。
* `src/rms/service/`：每个表的 RM FastAPI 前端。
* `scripts/`：用于 MySQL 引导和服务编排的辅助脚本。
* `test/`：针对 RM、TM 和 WC 集成的分阶段测试。
