from abc import ABC, abstractmethod
from typing import Tuple, Any


class PageIndex(ABC):
    """
    PageIndex defines the mapping between logical records and logical pages.
    This is a pure interface and should not contain any stateful logic.
    """

    @abstractmethod
    def record_to_page(self, record_key: Any) -> int:
        """Map a record key to a logical page id."""
        pass

    @abstractmethod
    def page_to_range(self, page_id: int) -> Tuple[Any, Any]:
        """
        Given a page id, return the (start_key, end_key) range
        used for page-in queries.
        """
        pass
