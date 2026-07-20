"""Database Connectors — connect to MySQL, PostgreSQL, MongoDB, SQLite."""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseDBConnector(ABC):

    @abstractmethod
    def test_connection(self) -> dict:
        pass

    @abstractmethod
    def get_tables(self) -> list:
        pass

    @abstractmethod
    def get_sample(self, table: str, limit: int = 5) -> dict:
        pass

    @abstractmethod
    def execute_query(self, query: str) -> dict:
        pass

    @abstractmethod
    def count_rows(self, table: str) -> int:
        pass

    def close(self):
        pass


class MySQLConnector(BaseDBConnector):

    def __init__(self, host, port, database, user, password):
        import pymysql
        self.conn = pymysql.connect(
            host=host, port=port or 3306, database=database,
            user=user, password=password, charset="utf8mb4",
            connect_timeout=10, cursorclass=pymysql.cursors.DictCursor,
        )

    def test_connection(self) -> dict:
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
            tables = self.get_tables()
            total = sum(t["row_count"] for t in tables)
            return {"success": True, "tables": tables, "total_rows": total}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_tables(self) -> list:
        tables = []
        with self.conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            names = [list(row.values())[0] for row in cur.fetchall()]
            for name in names:
                cur.execute(f"DESCRIBE `{name}`")
                columns = [{"name": r["Field"], "type": r["Type"]} for r in cur.fetchall()]
                cur.execute(f"SELECT COUNT(*) as cnt FROM `{name}`")
                count = cur.fetchone()["cnt"]
                tables.append({"name": name, "columns": columns, "row_count": count})
        return tables

    def get_sample(self, table: str, limit: int = 5) -> dict:
        return self.execute_query(f"SELECT * FROM `{table}` LIMIT {limit}")

    def execute_query(self, query: str) -> dict:
        try:
            with self.conn.cursor() as cur:
                q = query.rstrip(";")
                if "LIMIT" not in q.upper() and q.upper().startswith("SELECT"):
                    q += " LIMIT 100"
                cur.execute(q)
                rows = cur.fetchall()
                columns = [d[0] for d in cur.description] if cur.description else []
                return {"success": True, "columns": columns, "rows": rows, "count": len(rows)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def count_rows(self, table: str) -> int:
        r = self.execute_query(f"SELECT COUNT(*) as cnt FROM `{table}`")
        return r["rows"][0]["cnt"] if r["success"] else 0

    def close(self):
        self.conn.close()


class SQLiteConnector(BaseDBConnector):

    def __init__(self, file_path, **kwargs):
        import sqlite3
        self.conn = sqlite3.connect(file_path)
        self.conn.row_factory = sqlite3.Row

    def test_connection(self) -> dict:
        try:
            self.conn.execute("SELECT 1")
            tables = self.get_tables()
            total = sum(t["row_count"] for t in tables)
            return {"success": True, "tables": tables, "total_rows": total}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_tables(self) -> list:
        tables = []
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        for row in cur.fetchall():
            name = row[0]
            cur.execute(f"PRAGMA table_info('{name}')")
            columns = [{"name": r[1], "type": r[2]} for r in cur.fetchall()]
            cur.execute(f"SELECT COUNT(*) FROM '{name}'")
            count = cur.fetchone()[0]
            tables.append({"name": name, "columns": columns, "row_count": count})
        return tables

    def get_sample(self, table: str, limit: int = 5) -> dict:
        return self.execute_query(f"SELECT * FROM '{table}' LIMIT {limit}")

    def execute_query(self, query: str) -> dict:
        try:
            cur = self.conn.cursor()
            q = query.rstrip(";")
            if "LIMIT" not in q.upper() and q.upper().startswith("SELECT"):
                q += " LIMIT 100"
            cur.execute(q)
            rows = [dict(r) for r in cur.fetchall()]
            columns = [d[0] for d in cur.description] if cur.description else []
            return {"success": True, "columns": columns, "rows": rows, "count": len(rows)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def count_rows(self, table: str) -> int:
        r = self.execute_query(f"SELECT COUNT(*) as cnt FROM '{table}'")
        return r["rows"][0]["cnt"] if r["success"] else 0

    def close(self):
        self.conn.close()


class MongoDBConnector(BaseDBConnector):

    def __init__(self, host, port, database, user="", password=""):
        from pymongo import MongoClient
        if user and password:
            uri = f"mongodb://{user}:{password}@{host}:{port or 27017}/{database}"
        else:
            uri = f"mongodb://{host}:{port or 27017}/{database}"
        self.client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        self.db = self.client[database]

    def test_connection(self) -> dict:
        try:
            self.client.admin.command("ping")
            tables = self.get_tables()
            total = sum(t["row_count"] for t in tables)
            return {"success": True, "tables": tables, "total_rows": total}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_tables(self) -> list:
        tables = []
        for name in self.db.list_collection_names():
            count = self.db[name].estimated_document_count()
            sample = list(self.db[name].find().limit(5))
            columns = []
            if sample:
                keys = set()
                for doc in sample:
                    keys.update(doc.keys())
                columns = [{"name": k, "type": type(sample[0].get(k, "")).__name__} for k in sorted(keys)]
            tables.append({"name": name, "columns": columns, "row_count": count})
        return tables

    def get_sample(self, table: str, limit: int = 5) -> dict:
        docs = list(self.db[table].find().limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        columns = list(docs[0].keys()) if docs else []
        return {"success": True, "columns": columns, "rows": docs, "count": len(docs)}

    def execute_query(self, query: str) -> dict:
        return self.get_sample(query, 100)

    def count_rows(self, table: str) -> int:
        return self.db[table].estimated_document_count()

    def close(self):
        self.client.close()


def create_connector(db_type: str, **params):
    """Factory — create the right connector."""
    connectors = {
        "mysql": MySQLConnector,
        "mariadb": MySQLConnector,
        "sqlite": SQLiteConnector,
        "mongodb": MongoDBConnector,
        "mongo": MongoDBConnector,
    }
    cls = connectors.get(db_type.lower())
    if not cls:
        raise ValueError(f"Unsupported: {db_type}. Supported: {list(connectors.keys())}")
    return cls(**params)