from src.rm.base.page import Page
from src.rm.base.page_pool import PagePool

class CommittedPagePool(PagePool):
    def __init__(self):
        self._pages = {}

    def has_page(self, page_id: int) -> bool:
        return page_id in self._pages

    def get_page(self, page_id: int) -> Page | None:
        return self._pages.get(page_id)

    def put_page(self, page_id: int, page) -> None:
        self._pages[page_id] = page

    def remove_page(self, page_id: int) -> None:
        self._pages.pop(page_id, None)

    def clear(self) -> None:
        self._pages.clear()
    
    def get_record_version(self, page_id, key: str) -> int:
        page = self.get_page(page_id)
        if page is None:
            return None
        record = page.get(key)
        if record is None:
            return None
        return record.version
