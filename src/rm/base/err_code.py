import enum

class ErrCode(enum.Enum):
    SUCCESS = 0

    # ---------- Client / semantic errors (usually non-retryable) ----------
    INVALID_ARGUMENT = 10        # key 格式不对、缺字段、参数非法等
    KEY_EXISTS = 11              # insert duplicate
    KEY_NOT_FOUND = 12           # update/delete on missing

    TXN_NOT_FOUND = 20           # xid 未注册/已结束/不在本 RM 侧
    TXN_STATE_ERROR = 21         # 事务状态非法：重复 prepare/commit/abort，或顺序错误

    # ---------- Concurrency / conflict (often retryable depending on policy) ----------
    TXN_CONFLICT = 30            # 总类：冲突（兼容您现有）
    LOCK_CONFLICT = 31           # try_lock 失败 / deadlock avoid
    VERSION_CONFLICT = 32        # OCC 版本校验失败
    WRITE_WRITE_CONFLICT = 33    # 可选：更语义化（如果你未来区分的话）

    # ---------- Storage / system (usually retryable or escalate) ----------
    IO_ERROR = 40                # page_in/page_out/db 读写失败
    TIMEOUT = 41                 # DB/锁等待超时（若未来支持 wait）
    INTERNAL_INVARIANT = 42      # committed page missing、shadow 状态不一致等（程序/状态不变量被破坏）

    UNKNOWN_ERROR = 99


class RMResult:
    def __init__(self, ok: bool, value=None, err=ErrCode.SUCCESS):
        self.ok = ok
        self.value = value
        self.err = err
