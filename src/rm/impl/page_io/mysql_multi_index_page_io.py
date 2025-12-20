import pymysql
from src.rm.base.page_io import PageIO
from src.rm.base.page_index import PageIndex
from src.rm.base.page import Page, Record

class MySQLMultiIndexPageIO(PageIO):
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

        # 解析复合主键
        key_columns = self.key_column.split("|")
        first_key = key_columns[0]

        sql = f"""
            SELECT *
            FROM {self.table}
            WHERE {first_key} >= %s AND {first_key} <= %s
        """

        cursor = self.conn.cursor()
        cursor.execute(sql, (start, end))
        rows = cursor.fetchall()

        records = {}

        for row in rows:
            # 构造复合 key，例如 "cust|HOTEL|000123"
            composite_key = "|".join(str(row[col]) for col in key_columns)

            records[composite_key] = Record(row)

        return Page(page_id=page_id, records=records)


    def page_out(self, page: Page) -> None:
        """
        Persist page records back to database.

        Semantics:
        - page.records: {logical_key -> Record}
        - logical_key is NOT used for persistence
        - primary key columns are read from record fields
        - deleted records are physically deleted
        """
        if not page.records:
            return

        cursor = self.conn.cursor()

        key_columns = self.key_column.split("|")

        # 用任意一条 record 推断列结构
        sample_record = next(iter(page.records.values()))
        all_columns = list(sample_record.keys())

        non_key_columns = [
            col for col in all_columns if col not in key_columns
        ]

        # ---------- 1. DELETE ----------
        delete_sql = f"""
            DELETE FROM {self.table}
            WHERE {" AND ".join(f"{col}=%s" for col in key_columns)}
        """

        delete_values = []

        for record in page.records.values():
            if record.deleted:
                delete_values.append(
                    tuple(record[col] for col in key_columns)
                )

        if delete_values:
            cursor.executemany(delete_sql, delete_values)

        # ---------- 2. UPSERT ----------
        upsert_records = [
            record for record in page.records.values()
            if not record.deleted
        ]

        if not upsert_records:
            self.conn.commit()
            return

        column_clause = ", ".join(all_columns)
        placeholders = ", ".join(["%s"] * len(all_columns))

        update_clause = ", ".join(
            f"{col}=VALUES({col})" for col in non_key_columns
        )

        upsert_sql = f"""
            INSERT INTO {self.table} ({column_clause})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {update_clause}
        """

        upsert_values = [
            tuple(record[col] for col in all_columns)
            for record in upsert_records
        ]

        cursor.executemany(upsert_sql, upsert_values)
        self.conn.commit()


