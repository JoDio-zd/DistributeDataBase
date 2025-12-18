import pymysql
from typing import Tuple
from src.rm.base.page_io import PageIO
from src.rm.base.page_index import PageIndex
from src.rm.base.page import Page, Record

class MySQLPageIO(PageIO):
    def __init__(
        self,
        conn: pymysql.connections.Connection,
        table: str,
        key_column: str,
        page_index: PageIndex,
    ):
        """
        conn        : MySQL connection
        table       : table name (e.g. FLIGHTS)
        key_column  : primary key column (e.g. flightNum)
        page_index  : PageIndex instance
        """
        self.conn = conn
        self.table = table
        self.key_column = key_column
        self.page_index = page_index

    def page_in(self, page_id) -> Page:
        start, end = self.page_index.page_to_range(page_id)

        sql = f"""
            SELECT *
            FROM {self.table}
            WHERE {self.key_column} >= %s AND {self.key_column} < %s
        """

        cursor = self.conn.cursor()
        cursor.execute(sql, (start, end))
        rows = cursor.fetchall()
        records = {row[self.key_column]: Record(row) for row in rows}
        return Page(page_id=page_id, records=records)

    def page_out(self, page: Page) -> None:
        """
        Persist page records back to database.

        Assumptions:
        - page.records is a dict: {key -> record}
        - record is a dict of column -> value
        - Primary key is included in record
        """
        if not page.records:
            return

        cursor = self.conn.cursor()

        # 所有 record 共享同一列结构
        sample_record = next(iter(page.records.values()))
        columns = list(sample_record.keys())

        column_clause = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        update_clause = ", ".join(
            f"{col}=VALUES({col})" for col in columns
        )

        sql = f"""
            INSERT INTO {self.table} ({column_clause})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {update_clause}
        """

        values = [
            tuple(record[col] for col in columns)
            for record in page.records.values()
        ]

        cursor.executemany(sql, values)
        self.conn.commit()


