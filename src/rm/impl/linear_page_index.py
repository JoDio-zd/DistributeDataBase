from src.rm.base.page_index import PageIndex

class LinearPageIndex(PageIndex):
    def __init__(self, page_size: int):
        self.page_size = page_size

    def record_to_page(self, record_key: int) -> int:
        return record_key // self.page_size

    def page_to_range(self, page_id: int) -> tuple[int, int]:
        start = page_id * self.page_size
        end = start + self.page_size
        return start, end