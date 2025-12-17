from src.rm.base.shadow_page_pool import ShadowPagePool

class SimpleShadowPagePool(ShadowPagePool):
    def __init__(self):
        self._pages = {}  # xid -> {page_id -> page}

    def has_page(self, xid: int, page_id: int) -> bool:
        return xid in self._pages and page_id in self._pages[xid]

    def get_page(self, xid: int, page_id: int):
        return self._pages[xid][page_id]

    def put_page(self, xid: int, page_id: int, page) -> None:
        self._pages.setdefault(xid, {})[page_id] = page

    def remove_txn(self, xid: int) -> None:
        self._pages.pop(xid, None)
