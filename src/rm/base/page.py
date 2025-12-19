from typing import List, Any, Dict, Iterable
from dataclasses import field, dataclass
import copy

class Record(dict):
    def __init__(self, data, version=0):
        super().__init__(data)
        self.version = version
        self.deleted = False

@dataclass
class Page:
    page_id: int
    records: Dict[str, Record] = field(default_factory=dict)
    last_commit_xid: int = 0

    def get(self, key: str):
        return self.records.get(key)

    def put(self, key: str, record: Record):
        self.records[key] = record

    def delete(self, key: str):
        self.records.pop(key, None)

    def values(self) -> Iterable[Record]:
        return self.records.values()

    def items(self):
        return self.records.items()