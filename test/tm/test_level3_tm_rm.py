import time
import requests


# =========================================================
# Config
# =========================================================

TM = "http://127.0.0.1:9001"
RM = "http://127.0.0.1:8001"
KEY_WIDTH = 4


# =========================================================
# Helpers
# =========================================================

def gen_key(tag):
    t = int(time.time() * 1000) % 10000
    return str((t + abs(hash(tag)) % 1000) % 10000).zfill(KEY_WIDTH)


def tm_start():
    return requests.post(f"{TM}/txn/start", timeout=3).json()["xid"]


def tm_commit(xid: int):
    return requests.post(f"{TM}/txn/commit", json={"xid": xid}, timeout=3)


def tm_abort(xid: int):
    return requests.post(f"{TM}/txn/abort", json={"xid": xid}, timeout=3)


def rm_insert(xid: int, key: str, seats=10, price=100):
    r = requests.post(
        f"{RM}/records",
        json={
            "xid": xid,
            "record": {
                "flightNum": key,
                "price": price,
                "numSeats": seats,
                "numAvail": seats,
            },
        },
        timeout=3,
    )
    return r


def rm_update(xid: int, key: str, updates: dict):
    r = requests.put(
        f"{RM}/records/{key}",
        json={"xid": xid, "updates": updates},
        timeout=3,
    )
    return r


def rm_delete(xid: int, key: str):
    # delete 是 query 参数 xid
    r = requests.delete(
        f"{RM}/records/{key}",
        params={"xid": xid},
        timeout=3,
    )
    return r


def rm_read(xid: int, key: str):
    r = requests.get(
        f"{RM}/records/{key}",
        params={"xid": xid},
        timeout=3,
    )
    return r


def reset_key(key: str, seats=10):
    """
    确保 key 存在且内容确定：
    - 尝试 delete（不存在也无所谓）
    - insert
    全部在独立 txn 内完成，避免污染被测 txn
    """
    xid = tm_start()

    # best-effort delete
    try:
        rm_delete(xid, key)
    except Exception:
        pass

    r = rm_insert(xid, key, seats=seats, price=100)
    assert r.status_code == 200

    c = tm_commit(xid).json()
    assert c["ok"] is True


# =========================================================
# Level3 Tests (Single RM)
# =========================================================

def test_level3_happy_path_single_rm():
    print("\n[LEVEL3] happy path (single RM)")

    key = gen_key("l3_single_happy")
    reset_key(key)

    xid = tm_start()

    r = rm_update(xid, key, {"price": 111})
    assert r.status_code == 200

    res = tm_commit(xid).json()
    assert res["ok"] is True

    print("  -> PASS")
    return True


def test_level3_prepare_fail_single_rm_ww_conflict():
    """
    用同一个 key 制造 WW / VERSION_CONFLICT：
    - T1 update(key)
    - T2 update(key) 并先 commit
    - T1 commit 应失败（prepare 阶段失败 → TM 返回 ok=False）
    """
    print("\n[LEVEL3] prepare fail via WW conflict (single RM)")

    key = gen_key("l3_single_ww")
    reset_key(key)

    xid1 = tm_start()
    xid2 = tm_start()

    # T1 write
    r = rm_update(xid1, key, {"price": 111})
    assert r.status_code == 200

    # T2 write & commit first
    r = rm_update(xid2, key, {"price": 222})
    assert r.status_code == 200
    c2 = tm_commit(xid2).json()
    assert c2["ok"] is True

    # T1 commit should fail at prepare
    c1 = tm_commit(xid1).json()
    assert c1["ok"] is False

    print("  -> PASS")
    return True


def test_level3_commit_retry_single_rm():
    print("\n[LEVEL3] commit retry (single RM)")

    key = gen_key("l3_single_retry")
    reset_key(key)

    xid = tm_start()

    r = rm_update(xid, key, {"price": 333})
    assert r.status_code == 200

    # first commit
    c1 = tm_commit(xid)
    assert c1.status_code == 200
    assert c1.json()["ok"] is True

    # replay commit
    c2 = tm_commit(xid)
    assert c2.status_code in (200, 409)  # 409: already COMMITTED
    # 如果 200：最好返回 ok=True
    if c2.status_code == 200:
        assert c2.json().get("ok", True) is True

    print("  -> PASS")
    return True


def test_level3_abort_idempotent_single_rm():
    print("\n[LEVEL3] abort idempotent (single RM)")

    key = gen_key("l3_single_abort")
    reset_key(key)

    xid = tm_start()
    r = rm_update(xid, key, {"price": 444})
    assert r.status_code == 200

    a1 = tm_abort(xid)
    assert a1.status_code == 200
    assert a1.json()["ok"] is True

    # replay abort
    a2 = tm_abort(xid)
    assert a2.status_code == 200
    assert a2.json()["ok"] is True

    print("  -> PASS")
    return True


# =========================================================
# Runner
# =========================================================

def run_level3_http_single_rm():
    tests = [
        test_level3_happy_path_single_rm,
        test_level3_prepare_fail_single_rm_ww_conflict,
        test_level3_commit_retry_single_rm,
        test_level3_abort_idempotent_single_rm,
    ]

    passed = 0
    for t in tests:
        try:
            if t():
                passed += 1
        except Exception as e:
            print("  -> FAIL:", e)

    print(f"\nLEVEL3 (single RM) RESULT: {passed}/{len(tests)} passed")


if __name__ == "__main__":
    run_level3_http_single_rm()
