from abc import ABC, abstractmethod
from src.rm.base.page import Page


class PageIO(ABC):
    """
    PageIO defines how logical pages are loaded from and stored to
    an underlying database system.
    """

    @abstractmethod
    def page_in(self, page_id: int) -> Page:
        """
        Load a logical page identified by page_id from the database.
        """
        pass

    @abstractmethod
    def page_out(self, page: Page) -> None:
        """
        Persist a logical page to the database.
        """
        pass
