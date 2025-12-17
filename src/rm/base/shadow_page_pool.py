from abc import ABC, abstractmethod
from src.rm.base.page_io import Page

class ShadowPagePool(ABC):
    @abstractmethod
    def has_page(self, xid: int, page_id: int) -> bool:
        pass

    @abstractmethod
    def get_page(self, xid: int, page_id: int) -> Page:
        pass

    @abstractmethod
    def put_page(self, xid: int, page_id: int, page: Page) -> None:
        pass

    @abstractmethod
    def remove_txn(self, xid: int) -> None:
        """Remove all shadow pages for a transaction"""
        pass
