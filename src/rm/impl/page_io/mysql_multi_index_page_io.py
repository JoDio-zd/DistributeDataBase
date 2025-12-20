import pymysql
from src.rm.base.page_io import PageIO
from src.rm.base.page_index import PageIndex
from src.rm.base.page import Page, Record
import logging

logger = logging.getLogger("rm")

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

        logger.info(
            "PageIO initialized: table=%s key=%s index=%s",
            table,
            key_column,
            type(page_index).__name__,
        )

    def page_in(self, page_id) -> Page:
        start, end = self.page_index.page_to_range(page_id)

        # 解析复合主键
        key_columns = self.key_column.split("|")
        first_key = key_columns[0]

        logger.debug(
            "PageIO.page_in: page=%s range=[%s, %s]",
            page_id, start, end
        )

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

        logger.info(
            "PageIO.page_in done: page=%s records=%d",
            page_id, len(records)
        )

        return Page(page_id=page_id, records=records)


    def page_out(self, page: Page) -> None:
        """
        Persist page records back to database.

        Semantics:
        - page.records: {logical_key -> Record}
        - logical_key is NOT used for persistence
        - primary key columns are defined by key_column
        - deleted records are physically deleted
        """
        if not page.records:
            logger.debug(
                "PageIO.page_out skip: page=%s (empty)",
                page.page_id
            )
            return

        cursor = self.conn.cursor()
        key_columns = self.key_column.split("|")
        logger.debug("key columns: %s", key_columns)
        sample_record = next(iter(page.records.values()))
        for col in key_columns:
            assert col in sample_record, f"missing primary key column: {col}"
        non_key_columns = [
            col for col in sample_record.keys()
            if col not in key_columns and col != self.key_column
        ]
        logger.debug("non key columns: %s", non_key_columns)
        all_columns = key_columns + non_key_columns

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
            logger.info(
                "PageIO.page_out delete: page=%s count=%d",
                page.page_id, len(delete_values)
            )
            cursor.executemany(delete_sql, delete_values)

        # ---------- 2. UPSERT ----------
        upsert_records = [
            record for record in page.records.values()
            if not record.deleted
        ]

        if not upsert_records:
            self.conn.commit()
            logger.info(
                "PageIO.page_out done: page=%s (only deletes)",
                page.page_id
            )
            return

        column_clause = ", ".join(all_columns)
        placeholders = ", ".join(["%s"] * len(all_columns))

        update_clause = ", ".join(
            f"{col}=VALUES({col})" for col in all_columns
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

        logger.info(
            "PageIO.page_out upsert: page=%s count=%d",
            page.page_id, len(upsert_records)
        )

        logger.debug("Upsert SQL: %s", upsert_sql)
        logger.debug("Upsert Values Sample: %s", upsert_values)

        cursor.executemany(upsert_sql, upsert_values)
        self.conn.commit()

        logger.info(
            "PageIO.page_out done: page=%s total=%d",
            page.page_id, len(page.records)
        )
