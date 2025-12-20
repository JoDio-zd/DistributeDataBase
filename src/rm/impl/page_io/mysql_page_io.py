import pymysql
import logging
from src.rm.base.page_io import PageIO
from src.rm.base.page_index import PageIndex
from src.rm.base.page import Page, Record

logger = logging.getLogger("rm")


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

        logger.info(
            "PageIO initialized: table=%s key=%s index=%s",
            table,
            key_column,
            type(page_index).__name__,
        )

    # =========================================================
    # Page In
    # =========================================================
    def page_in(self, page_id) -> Page:
        start, end = self.page_index.page_to_range(page_id)

        logger.debug(
            "PageIO.page_in: page=%s range=[%s, %s]",
            page_id, start, end
        )

        sql = f"""
            SELECT *
            FROM {self.table}
            WHERE {self.key_column} >= %s AND {self.key_column} <= %s
        """

        cursor = self.conn.cursor()
        cursor.execute(sql, (start, end))
        rows = cursor.fetchall()

        records = {
            row[self.key_column]: Record(row)
            for row in rows
        }

        logger.info(
            "PageIO.page_in done: page=%s records=%d",
            page_id, len(records)
        )

        return Page(page_id=page_id, records=records)

    # =========================================================
    # Page Out
    # =========================================================
    def page_out(self, page: Page) -> None:
        """
        Persist page records back to database.
        """
        if not page.records:
            logger.debug(
                "PageIO.page_out skip: page=%s (empty)",
                page.page_id
            )
            return

        cursor = self.conn.cursor()

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

        logger.info(
            "PageIO.page_out upsert: page=%s count=%d",
            page.page_id, len(values)
        )

        logger.debug("Upsert SQL: %s", sql)

        cursor.executemany(sql, values)
        self.conn.commit()

        logger.info(
            "PageIO.page_out done: page=%s",
            page.page_id
        )
