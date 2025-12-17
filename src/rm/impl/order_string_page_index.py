from src.rm.base.page_index import PageIndex


class OrderedStringPageIndex(PageIndex):
    """
    PageIndex based on lexicographically ordered, normalized string keys.
    """

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
        """
        Map a record key to a logical page id by prefix extraction.

        The page id is defined as the prefix of the key, excluding
        the offset part. This preserves lexicographic order and
        defines a stable logical key range.

        Args:
            record_key (str):
                Record key. Will be left-padded with '0' if shorter
                than key_width.

        Returns:
            str:
                Logical page id (key prefix).
        """
        if len(record_key) < self.key_width:
            record_key = record_key.zfill(self.key_width)

        prefix_len = self.key_width - self.page_size
        return record_key[:prefix_len]

    def page_to_range(self, page_id: str):
        """
        Get the key range covered by a logical page.

        A page is defined by a key prefix (page_id).
        All keys starting with this prefix belong to the page.

        Returns:
            (start_key, end_key):
                Lexicographic range [start_key, end_key)
        """
        # Smallest possible suffix
        min_suffix = "0" * self.page_size

        # Largest possible suffix (exclusive upper bound)
        # Using 'Z' assumes charset is 0-9A-Z
        max_suffix = "Z" * self.page_size

        start_key = page_id + min_suffix
        end_key = page_id + max_suffix

        return start_key, end_key
