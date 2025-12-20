from src.rm.base.page_index import PageIndex

class DirectPageIndex(PageIndex):
    def __init__(self, page_size: int, key_width: int):
        """
        Args:
            page_size (int):
                Lens of the offset part of the key.
                For example, page_size=3 for keys like "00012",

            key_width (int):
                Fixed width of normalized string keys.
                For example, key_width=5 for keys like "00012".
        """
        self.page_size = page_size
        self.key_width = key_width

    def record_to_page(self, record_key: str) -> str:
        prefix_len = self.key_width - self.page_size
        return record_key[:prefix_len]

    def page_to_range(self, page_id: str) -> str:
        start = page_id
        end = page_id
        return start, end