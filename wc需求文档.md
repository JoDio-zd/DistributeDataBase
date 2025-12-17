# 需求文档：Workflow Controller（WC）—Python 实现（RESTful API + 分布式事务编排）

## 1. 目标与范围

### 1.1 目标

实现一个 **Workflow Controller（WC）** 服务，作为客户端唯一可见入口，提供：

* 全局事务生命周期管理的对外接口：**start / commit / abort**
* 面向业务的统一 RESTful API：**add / query / update / delete / reserve**
* 与 **1 个 TM（Transaction Manager）+ 4 个 RM（Resource Manager）** 的远程通信与编排能力
* 故障注入与恢复辅助能力：**die() / reconnect()**

### 1.2 实现范围（只做 WC）

本项目仅实现 **WC**。TM 与 RM 不在本项目实现范围内，但 WC 必须按约定与其通信。

### 1.3 关键约束

* **必须使用 Python 开发**
* 采用 **RESTful API**（HTTP + JSON）
* 事务上下文通过统一方式透传（强制要求）：**HTTP Header `X-Transaction-Id`**

---

## 2. 系统架构与依赖（对齐给定架构图）

### 2.1 组件

* **Client**：仅调用 WC
* **WC**：唯一客户端入口，负责编排与协调
* **TM**：全局事务协调者，负责 2PC（prepare/commit/abort）
* **四个 RM**：资源管理器（Flights / Hotels / Cars / Customers）

### 2.2 WC 必须维护的 5 个 Remote Reference（硬性要求）

WC 内部必须持有并使用如下 5 个远程引用（HTTP 客户端或等价抽象）：

1. `TM Remote Reference`
2. `Flights RM Remote Reference`
3. `Hotels RM Remote Reference`
4. `Cars RM Remote Reference`
5. `Customers RM Remote Reference`

### 2.3 数据划分（逻辑表）

* FLIGHTS(flightNum, price, numSeats, numAvail)
* HOTELS(location, price, numRooms, numAvail)
* CARS(location, price, numCars, numAvail)
* CUSTOMERS(custName)
* RESERVATIONS(custName, resvType, resvKey)

**RM 数据归属要求：**

* Flights RM：FLIGHTS
* Hotels RM：HOTELS
* Cars RM：CARS
* Customers RM：CUSTOMERS + RESERVATIONS

---

## 3. WC 的职责需求（必须完成的工作）

### 3.1 对外职责（Client-facing）

1. **提供唯一入口接口**
   客户端只能通过 WC 完成所有事务与业务操作。
2. **事务编排（Orchestration）**
   针对跨 RM 操作（尤其 reserve），WC 必须按业务语义协调对多个 RM 的调用顺序与失败处理。
3. **事务上下文透传**
   WC 必须将 `X-Transaction-Id` 原样传递给每一次对 RM/TM 的相关调用（除 start）。
4. **统一错误映射与一致性策略**
   当某业务步骤失败时，WC 必须给出明确的失败响应，并在需要时触发 abort（见第 6 节语义要求）。
5. **维护接口（PPT 要求）**
   提供 `die()` 与 `reconnect()` 的对外接口，用于模拟异常与重连恢复。

### 3.2 对内职责（Internal）

1. **远程调用封装**
   需要对 TM/RM 的 HTTP 调用进行封装：超时、错误处理、响应解析、Header 注入。
2. **跨 RM 聚合业务的实现**
   例如 reserve 操作必须涉及库存 RM 与 Customers RM 的 RESERVATIONS 写入。
3. **可观测性（最低要求）**
   对每个请求记录：xid、目标 RM/TM、调用耗时、返回码/异常原因，以便定位分布式事务问题。

---

## 4. 对外 RESTful API 需求（WC 暴露给客户端）

### 4.1 事务生命周期 API（硬性要求）

#### 4.1.1 Start（必须返回 xid）

* `POST /transactions`
* 返回：`201 Created`

```json
{ "xid": "<string>", "status": "ACTIVE" }
```

* 语义要求：

  * WC 必须调用 TM 创建全局事务，并将 TM 返回的 xid 返回给客户端
  * xid 必须作为后续所有业务请求的 `X-Transaction-Id`

#### 4.1.2 Commit

* `POST /transactions/{xid}/commit`
* 返回（成功）：`200 OK`

```json
{ "xid": "<string>", "status": "COMMITTED" }
```

* 语义要求：

  * WC 必须调用 TM 执行提交，由 TM 驱动 2PC
  * WC 不得绕过 TM 直接命令 RM commit

#### 4.1.3 Abort

* `POST /transactions/{xid}/abort`
* 返回（成功）：`200 OK`

```json
{ "xid": "<string>", "status": "ABORTED" }
```

#### 4.1.4 Transaction Status（建议但强烈要求实现）

* `GET /transactions/{xid}`
* 返回：`200 OK`

```json
{ "xid": "<string>", "status": "ACTIVE|PREPARING|COMMITTED|ABORTED|IN_DOUBT" }
```

* 用于 commit 超时或 reconnect 后查询最终决议

---

### 4.2 业务资源 API（必须支持 aduq + reserve）

**通用要求：**

* 除 `POST /transactions` 外，所有会读写一致性视图的业务接口都必须支持 `X-Transaction-Id` Header
* `DELETE` 必须使用 HTTP DELETE（你已明确决定）

#### 4.2.1 Flights

* `POST /flights`（add）
* `GET /flights/{flightNum}`（query）
* `PATCH /flights/{flightNum}`（update/change）
* `DELETE /flights/{flightNum}`（delete）
* `POST /flights/{flightNum}/reservations`（reserveFlight，跨 RM）

#### 4.2.2 Hotels

* `POST /hotels`
* `GET /hotels/{location}`
* `PATCH /hotels/{location}`
* `DELETE /hotels/{location}`
* `POST /hotels/{location}/reservations`（reserveHotel，跨 RM）

#### 4.2.3 Cars

* `POST /cars`
* `GET /cars/{location}`
* `PATCH /cars/{location}`
* `DELETE /cars/{location}`
* `POST /cars/{location}/reservations`（reserveCar，跨 RM）

#### 4.2.4 Customers / Reservations

* `POST /customers`（add customer）
* `GET /customers/{custName}`（query customer）
* `DELETE /customers/{custName}`（delete customer）
* `GET /customers/{custName}/reservations`（query reservations）

---

### 4.3 维护与故障注入 API（必须实现）

* `POST /admin/die`

  * 语义：模拟 WC 异常（可选择立即退出进程或进入不可用状态）
* `POST /admin/reconnect`

  * 语义：WC 重新连接 TM 与 4 个 RM，并触发必要的状态检查（详见第 7 节）

---

## 5. WC 内部业务编排需求（核心）

### 5.1 Reserve 的跨 RM 原子性要求（硬性）

Reserve 操作必须拆解为至少两个步骤，并在同一个 xid 下执行：

* Step A：调用对应库存 RM（Flights/Hotels/Cars）执行占用（例如 `numAvail--` 的事务内变更）
* Step B：调用 Customers RM 写入 RESERVATIONS(custName, resvType, resvKey)

**要求：**

* 两个步骤必须使用同一个 `X-Transaction-Id`
* 任一步失败时 WC 必须按第 6 节策略处理（通常触发 abort）
* 最终一致性由 TM 的 2PC 在 commit 时保证

### 5.2 示例约束（必须能支持以下调用序列）

* 客户端：start → query(酒店/航班) → reserveFlight + reserveHotel → commit
  WC 必须正确路由到对应 RM，并在 commit 时调用 TM 完成全局提交。

---

## 6. 事务语义与错误处理需求（必须明确执行）

### 6.1 DELETE 的事务语义（必须对齐 Shadow Page 模式）

* 客户端 `DELETE /resource/{key}`（带 xid）仅表示**事务内删除意图**
* 删除真正生效必须在 `commit(xid)` 完成后才可见（由 RM 的 shadow page → commit 落库实现）

### 6.2 失败处理策略（WC 行为要求）

* 当 WC 在一次事务内编排的任意业务步骤失败（RM 返回 4xx/5xx 或超时）：

  * WC 必须返回错误给客户端
  * WC 必须支持“自动回滚策略”：默认触发 `POST /transactions/{xid}/abort`（除非你后续明确要求改为由客户端决定）
* commit 超时/不确定：

  * WC 必须提示客户端通过 `GET /transactions/{xid}` 查询最终状态（或返回 IN_DOUBT）

### 6.3 幂等性最低要求

* `POST /transactions/{xid}/commit` 必须幂等：重复调用返回同一最终状态
* `POST /transactions/{xid}/abort` 必须幂等
* reserve 的幂等性可选（建议支持 `Idempotency-Key`，但不是硬性要求，除非你后续要求）

---

## 7. reconnect() 行为需求（PPT 要求，必须实现）

`POST /admin/reconnect` 必须完成以下动作：

1. **重建与 TM + 4 RM 的连接**（更新/验证 baseUrl 可用性）
2. **尝试处理未正确结束的事务**的最小支持：

   * WC 向 TM 查询事务状态（至少支持查询指定 xid 或列出活动 xid；由 TM 能力决定）
   * WC 必须保证：即使 WC 曾崩溃，客户端仍可通过 WC 查询事务状态并继续提交/回滚请求
3. reconnect 时必须同时尝试重连 TM 与所有 RM（你已明确要求）

> 说明：事务最终决议与恢复推进仍应由 TM 负责；WC 的 reconnect 侧重“恢复可用性 + 提供状态可查 + 允许客户端继续操作”。

---

## 8. 与 TM/RM 的接口契约要求（WC 依赖的外部能力）

由于项目只实现 WC，但 WC 必须假设 TM/RM 提供如下能力（否则 WC 无法工作）。这些是**外部系统必须满足的契约**：

### 8.1 TM 必须提供（WC 调用）

* 创建事务并返回 xid
* commit/abort 指令
* 查询事务状态（用于不确定状态与 reconnect）

### 8.2 RM 必须提供（WC 调用）

* 对应资源的 add/query/update/delete
* reserve（或等价的库存占用接口）
* 所有接口接受 `X-Transaction-Id` 并按事务隔离写入 shadow page

### 8.3 enlist（架构一致性要求）

* RM 在首次参与 xid 时需要向 TM enlist（该流程由 RM→TM 完成）
* WC 不负责显式 enlist，但必须保证 xid 透传，从而触发 RM 的 enlist 逻辑

---

## 9. 配置与部署需求（WC）

### 9.1 必须可配置项

* WC 服务监听地址与端口
* TM base URL
* 四个 RM base URL（flights/hotels/cars/customers）
* HTTP 超时参数（建议区分连接/读超时）
* 日志级别

### 9.2 运行形态要求

* WC 必须作为独立 HTTP 服务运行
* 可本地运行示例：`127.0.0.1:<wcPort>/...`，并按端口访问各 RM：`127.0.0.1:<rmPort>/...`

---

## 10. 验收标准（完成度判定）

WC 实现完成需满足至少以下验收点：

1. `POST /transactions` 返回 xid，后续接口可使用该 xid
2. 对 flights/hotels/cars/customers 的 CRUD 均可通过 WC 访问，并正确路由到对应 RM
3. `DELETE` 全部使用 HTTP DELETE 且支持事务语义（在 commit 前不应在已提交视图中生效）
4. reserve 能完成跨 RM 的两阶段业务调用（库存扣减 + reservations 写入），并在 commit 后一致生效
5. `commit/abort` 由 WC 调用 TM 触发，WC 不直接对 RM 发 commit/abort
6. `POST /admin/reconnect` 可重连 TM 与 RM，并支持继续查询/提交/回滚未结束事务
7. `POST /admin/die` 可模拟 WC 异常（用于事务鲁棒性测试）
