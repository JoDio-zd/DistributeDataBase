# API 接口契约规范

本文档定义了 Workflow Controller (WC) 与 Transaction Manager (TM) 和 Resource Managers (RM) 之间的 HTTP API 接口契约。

## 目的

- 为 WC 实现提供明确的接口依据
- 作为 TM/RM 开发者的接口规范参考
- 确保各组件之间的互操作性

## 通用约定

### 1. 事务上下文透传

所有涉及事务的请求（除 `POST /transactions` 外）必须在 HTTP Header 中包含事务ID：

```
X-Transaction-Id: {xid}
```

### 2. 响应格式

所有响应使用 JSON 格式，Content-Type 为 `application/json`。

### 3. 错误响应

```json
{
  "error": "错误描述",
  "details": "详细错误信息（可选）"
}
```

常见HTTP状态码：
- `200 OK`: 成功
- `201 Created`: 资源创建成功
- `204 No Content`: 成功但无返回内容（如DELETE）
- `400 Bad Request`: 请求参数错误
- `404 Not Found`: 资源不存在
- `409 Conflict`: 资源冲突（如库存不足）
- `500 Internal Server Error`: 服务器内部错误
- `503 Service Unavailable`: 服务不可用

---

## TM (Transaction Manager) 接口规范

**Base URL**: 可配置（默认: `http://localhost:8001`）

### 1. 创建事务

**描述**: 创建一个新的全局事务并返回事务ID (xid)

**请求**:
```http
POST /transactions
Content-Type: application/json
```

**响应**:
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "xid": "tx_20231217_001234",
  "status": "ACTIVE"
}
```

**说明**:
- `xid`: 全局唯一的事务标识符，由TM生成
- `status`: 事务状态，新创建的事务状态为 `ACTIVE`

---

### 2. 提交事务 (Commit)

**描述**: 提交一个事务，触发两阶段提交协议 (2PC)

**请求**:
```http
POST /transactions/{xid}/commit
Content-Type: application/json
```

**响应（成功）**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "xid": "tx_20231217_001234",
  "status": "COMMITTED"
}
```

**响应（超时/不确定）**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "xid": "tx_20231217_001234",
  "status": "IN_DOUBT",
  "message": "Commit operation timed out, status uncertain"
}
```

**说明**:
- TM 协调所有参与的 RM 执行 2PC 协议
- 如果超时，返回 `IN_DOUBT` 状态，客户端应通过 GET /transactions/{xid} 查询最终状态
- **幂等性**: 重复调用返回相同结果

---

### 3. 回滚事务 (Abort)

**描述**: 回滚一个事务，撤销所有未提交的修改

**请求**:
```http
POST /transactions/{xid}/abort
Content-Type: application/json
```

**响应**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "xid": "tx_20231217_001234",
  "status": "ABORTED"
}
```

**说明**:
- TM 通知所有参与的 RM 回滚事务
- **幂等性**: 重复调用返回相同结果
- 即使某些 RM 已经不可达，TM 应确保事务最终被标记为 ABORTED

---

### 4. 查询事务状态

**描述**: 查询事务的当前状态

**请求**:
```http
GET /transactions/{xid}
```

**响应**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "xid": "tx_20231217_001234",
  "status": "COMMITTED"
}
```

**状态枚举**:
- `ACTIVE`: 事务活跃中，可以执行操作
- `PREPARING`: 正在执行 prepare 阶段
- `COMMITTED`: 事务已成功提交
- `ABORTED`: 事务已回滚
- `IN_DOUBT`: 事务状态不确定（commit超时）

**错误响应**:
```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "error": "Transaction not found"
}
```

---

## RM (Resource Manager) 接口规范

### Base URLs

- **Flights RM**: `http://localhost:8002` (端口 33061 映射)
- **Hotels RM**: `http://localhost:8003` (端口 33062 映射)
- **Cars RM**: `http://localhost:8004` (端口 33063 映射)
- **Customers RM**: `http://localhost:8005` (端口 33064 映射)

### 通用规则

1. **X-Transaction-Id Header**: 所有修改操作必须包含此 header
2. **Enlist机制**: RM 在首次收到某个 xid 的请求时，自动向 TM 注册（enlist）
3. **Shadow Page**: 所有修改在 commit 前都存储在 shadow page 中，不影响已提交的数据
4. **读操作**: 读取时优先返回当前事务的 shadow page 数据，如果不存在则返回已提交数据

---

## Flights RM 接口

### 1. 添加航班 (Add Flight)

**请求**:
```http
POST /flights
X-Transaction-Id: {xid}
Content-Type: application/json

{
  "flightNum": "CA1234",
  "price": 1000,
  "numSeats": 200,
  "numAvail": 200
}
```

**响应**:
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "flightNum": "CA1234",
  "price": 1000,
  "numSeats": 200,
  "numAvail": 200
}
```

**错误**:
- `400 Bad Request`: 参数错误（如缺少字段）
- `409 Conflict`: 航班号已存在

---

### 2. 查询航班 (Query Flight)

**请求**:
```http
GET /flights/{flightNum}
X-Transaction-Id: {xid}  # 可选
```

**响应**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "flightNum": "CA1234",
  "price": 1000,
  "numSeats": 200,
  "numAvail": 180
}
```

**错误**:
- `404 Not Found`: 航班不存在

**说明**:
- 如果提供 xid，返回该事务视图的数据（包括未提交修改）
- 如果不提供 xid，返回已提交的数据

---

### 3. 更新航班 (Update Flight)

**请求**:
```http
PATCH /flights/{flightNum}
X-Transaction-Id: {xid}
Content-Type: application/json

{
  "price": 1200,
  "numAvail": 150
}
```

**响应**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "flightNum": "CA1234",
  "price": 1200,
  "numSeats": 200,
  "numAvail": 150
}
```

**说明**:
- 支持部分更新（只更新提供的字段）
- 修改存储在 shadow page 中，commit 后才生效

---

### 4. 删除航班 (Delete Flight)

**请求**:
```http
DELETE /flights/{flightNum}
X-Transaction-Id: {xid}
```

**响应**:
```http
HTTP/1.1 204 No Content
```

**说明**:
- 删除操作在 shadow page 中标记，commit 后才真正删除
- 在当前事务中，后续查询该航班将返回 404

---

### 5. 预留航班 (Reserve Flight)

**描述**: 减少可用座位数 (numAvail--)，用于预订

**请求**:
```http
POST /flights/{flightNum}/reserve
X-Transaction-Id: {xid}
Content-Type: application/json

{
  "quantity": 1
}
```

**响应（成功）**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": true,
  "numAvail": 179
}
```

**响应（库存不足）**:
```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "error": "Insufficient availability",
  "details": "Requested: 1, Available: 0"
}
```

**说明**:
- 原子性地减少 numAvail
- 如果 numAvail < quantity，返回 409 错误
- 修改存储在 shadow page 中

---

## Hotels RM 接口

**结构与 Flights RM 完全相同**，仅资源名称和字段不同：

### 数据模型

```json
{
  "location": "Shanghai",
  "price": 500,
  "numRooms": 100,
  "numAvail": 80
}
```

### 端点

- `POST /hotels` - 添加酒店
- `GET /hotels/{location}` - 查询酒店
- `PATCH /hotels/{location}` - 更新酒店
- `DELETE /hotels/{location}` - 删除酒店
- `POST /hotels/{location}/reserve` - 预留房间

---

## Cars RM 接口

**结构与 Flights RM 完全相同**，仅资源名称和字段不同：

### 数据模型

```json
{
  "location": "Beijing",
  "price": 300,
  "numCars": 50,
  "numAvail": 40
}
```

### 端点

- `POST /cars` - 添加租车
- `GET /cars/{location}` - 查询租车
- `PATCH /cars/{location}` - 更新租车
- `DELETE /cars/{location}` - 删除租车
- `POST /cars/{location}/reserve` - 预留车辆

---

## Customers RM 接口

### 1. 添加客户 (Add Customer)

**请求**:
```http
POST /customers
X-Transaction-Id: {xid}
Content-Type: application/json

{
  "custName": "Alice"
}
```

**响应**:
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "custName": "Alice"
}
```

---

### 2. 查询客户 (Query Customer)

**请求**:
```http
GET /customers/{custName}
X-Transaction-Id: {xid}  # 可选
```

**响应**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "custName": "Alice"
}
```

---

### 3. 删除客户 (Delete Customer)

**请求**:
```http
DELETE /customers/{custName}
X-Transaction-Id: {xid}
```

**响应**:
```http
HTTP/1.1 204 No Content
```

**说明**:
- 删除客户时应同时删除其所有预订记录（级联删除）

---

### 4. 添加预订记录 (Add Reservation)

**描述**: 为客户添加一条预订记录（由 WC 在 reserve 操作的第二步调用）

**请求**:
```http
POST /reservations
X-Transaction-Id: {xid}
Content-Type: application/json

{
  "custName": "Alice",
  "resvType": "FLIGHT",
  "resvKey": "CA1234"
}
```

**响应**:
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "custName": "Alice",
  "resvType": "FLIGHT",
  "resvKey": "CA1234"
}
```

**说明**:
- `resvType`: 枚举类型，可选值: `FLIGHT`, `HOTEL`, `CAR`
- `resvKey`: 对应的资源标识（flightNum 或 location）
- 主键: `(custName, resvType, resvKey)`

---

### 5. 查询客户预订记录 (Query Customer Reservations)

**请求**:
```http
GET /customers/{custName}/reservations
X-Transaction-Id: {xid}  # 可选
```

**响应**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "custName": "Alice",
  "reservations": [
    {
      "resvType": "FLIGHT",
      "resvKey": "CA1234"
    },
    {
      "resvType": "HOTEL",
      "resvKey": "Shanghai"
    }
  ]
}
```

---

## WC 调用流程示例

### 示例 1: 简单查询操作

```
Client -> WC: POST /transactions
WC -> TM: POST /transactions
TM -> WC: {"xid": "tx_001", "status": "ACTIVE"}
WC -> Client: {"xid": "tx_001", "status": "ACTIVE"}

Client -> WC: GET /flights/CA1234 (X-Transaction-Id: tx_001)
WC -> Flights RM: GET /flights/CA1234 (X-Transaction-Id: tx_001)
Flights RM -> WC: {"flightNum": "CA1234", "price": 1000, ...}
WC -> Client: {"flightNum": "CA1234", "price": 1000, ...}

Client -> WC: POST /transactions/tx_001/commit
WC -> TM: POST /transactions/tx_001/commit
TM -> WC: {"xid": "tx_001", "status": "COMMITTED"}
WC -> Client: {"xid": "tx_001", "status": "COMMITTED"}
```

---

### 示例 2: Reserve 操作（跨 RM）

```
Client -> WC: POST /transactions
WC -> TM: POST /transactions
TM -> WC: {"xid": "tx_002", "status": "ACTIVE"}

Client -> WC: POST /flights/CA1234/reservations {"custName": "Bob"}
                (X-Transaction-Id: tx_002)

WC -> Flights RM: POST /flights/CA1234/reserve (X-Transaction-Id: tx_002)
                  {"quantity": 1}
Flights RM -> WC: {"success": true, "numAvail": 179}

WC -> Customers RM: POST /reservations (X-Transaction-Id: tx_002)
                    {"custName": "Bob", "resvType": "FLIGHT", "resvKey": "CA1234"}
Customers RM -> WC: 201 Created

WC -> Client: 201 Created

Client -> WC: POST /transactions/tx_002/commit
WC -> TM: POST /transactions/tx_002/commit
TM -> (prepare) Flights RM, Customers RM
TM -> (commit) Flights RM, Customers RM
TM -> WC: {"xid": "tx_002", "status": "COMMITTED"}
WC -> Client: {"xid": "tx_002", "status": "COMMITTED"}
```

---

### 示例 3: 错误处理与自动回滚

```
Client -> WC: POST /transactions
WC -> TM: {"xid": "tx_003"}

Client -> WC: POST /flights/CA1234/reservations {"custName": "Charlie"}

WC -> Flights RM: POST /flights/CA1234/reserve
Flights RM -> WC: 409 Conflict {"error": "Insufficient availability"}

WC -> TM: POST /transactions/tx_003/abort (自动触发)
TM -> WC: {"xid": "tx_003", "status": "ABORTED"}

WC -> Client: 409 Conflict
              {"error": "Insufficient availability", "transaction_aborted": true}
```

---

## 接口实现检查清单

### TM 实现者

- [ ] POST /transactions - 生成全局唯一 xid
- [ ] POST /transactions/{xid}/commit - 实现 2PC 协议
- [ ] POST /transactions/{xid}/abort - 通知所有 RM 回滚
- [ ] GET /transactions/{xid} - 查询事务状态
- [ ] Enlist机制 - 接受 RM 的 enlist 请求
- [ ] 超时处理 - commit 超时返回 IN_DOUBT

### RM 实现者

- [ ] 所有修改操作接受 X-Transaction-Id header
- [ ] 首次收到 xid 时向 TM enlist
- [ ] 实现 shadow page 机制
- [ ] 实现 prepare/commit/abort 接口（供 TM 调用）
- [ ] DELETE 操作支持事务语义
- [ ] Reserve 操作检查库存并原子性扣减

### WC 实现者

- [ ] 所有对 RM/TM 的调用注入 X-Transaction-Id
- [ ] Reserve 操作编排两个步骤（库存扣减 + 预订记录）
- [ ] 错误自动触发 abort
- [ ] Commit 超时处理
- [ ] 结构化日志记录（包含 xid）

---

## 附录：数据库表结构

### FLIGHTS (Flights RM)

```sql
CREATE TABLE FLIGHTS (
    flightNum VARCHAR(20) PRIMARY KEY,
    price INT NOT NULL,
    numSeats INT NOT NULL,
    numAvail INT NOT NULL
);
```

### HOTELS (Hotels RM)

```sql
CREATE TABLE HOTELS (
    location VARCHAR(100) PRIMARY KEY,
    price INT NOT NULL,
    numRooms INT NOT NULL,
    numAvail INT NOT NULL
);
```

### CARS (Cars RM)

```sql
CREATE TABLE CARS (
    location VARCHAR(100) PRIMARY KEY,
    price INT NOT NULL,
    numCars INT NOT NULL,
    numAvail INT NOT NULL
);
```

### CUSTOMERS (Customers RM)

```sql
CREATE TABLE CUSTOMERS (
    custName VARCHAR(100) PRIMARY KEY
);

CREATE TABLE RESERVATIONS (
    custName VARCHAR(100),
    resvType ENUM('FLIGHT', 'HOTEL', 'CAR'),
    resvKey VARCHAR(100),
    PRIMARY KEY (custName, resvType, resvKey),
    FOREIGN KEY (custName) REFERENCES CUSTOMERS(custName) ON DELETE CASCADE
);
```

---

## 版本历史

- **v1.0** (2023-12-17): 初始版本
  - 定义 TM 接口规范
  - 定义 4 个 RM 接口规范
  - 定义 reserve 跨 RM 操作流程
  - 定义错误处理规范
