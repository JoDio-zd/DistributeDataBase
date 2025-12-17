from typing import List, Any, Dict, Iterable
from dataclasses import field, dataclass
Record = dict

@dataclass
class Page:
    page_id: int
    records: Dict[str, Record] = field(default_factory=dict)

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