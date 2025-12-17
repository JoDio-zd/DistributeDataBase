from abc import ABC, abstractmethod
from typing import Optional
from src.rm.base.page_io import Page

class PagePool(ABC):
    @abstractmethod
    def has_page(self, page_id: int) -> bool:
        pass

    @abstractmethod
    def get_page(self, page_id: int) -> Page | None:
        pass

    @abstractmethod
    def put_page(self, page_id: int, page: Page) -> None:
        pass

    @abstractmethod
    def remove_page(self, page_id: int) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass
