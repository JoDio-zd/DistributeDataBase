from src.rm.base.err_code import ErrCode
from fastapi import HTTPException

ERR_HTTP_MAP = {
    ErrCode.KEY_EXISTS: 409,
    ErrCode.KEY_NOT_FOUND: 404,
    ErrCode.LOCK_CONFLICT: 409,
    ErrCode.VERSION_CONFLICT: 409,
    ErrCode.TXN_NOT_FOUND: 400,
    ErrCode.INTERNAL_INVARIANT: 500,
}

def handle_rm_result(res):
    if res.ok:
        return res.value
    status = ERR_HTTP_MAP.get(res.err, 500)
    raise HTTPException(
        status_code=status,
        detail=res.err.name,
    )
