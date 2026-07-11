import duckdb
import logging
from typing import List, Dict, Any
from openclaw.rbac.policy import OPENCLAW_POLICY

logger = logging.getLogger(__name__)

class ReadOnlyDuckDBConnection:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._validate_startup()
    
    def _validate_startup(self):
        con = duckdb.connect(self.db_path, read_only=False)
        try:
            for t in OPENCLAW_POLICY.writable_tables:
                table_short = t.value.split(".")[-1]
                result = con.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{table_short}'").fetchall()
                if not result:
                    raise RuntimeError(f"Table {table_short} does not exist.")
        finally:
            con.close()
    
    def query(self, sql: str, table_hint: str = None) -> List[Dict[str, Any]]:
        forbidden = ["INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE", "TRUNCATE"]
        if any(kw in sql.upper() for kw in forbidden):
            raise PermissionError("Write operation denied")
        if "SELECT *" in sql.upper():
            raise PermissionError("SELECT * denied")
        con = duckdb.connect(self.db_path, read_only=True)
        try:
            result = con.execute(sql).fetchall()
            cols = [desc[0] for desc in con.description] if con.description else []
            return [dict(zip(cols, row)) for row in result]
        finally:
            con.close()
    
    def insert(self, table: str, data: List[Dict[str, Any]]) -> int:
        if not OPENCLAW_POLICY.can_write(table):
            raise PermissionError("Table not writable")
        if not data:
            return 0
        con = duckdb.connect(self.db_path, read_only=False)
        try:
            for row in data:
                cols = ",".join(row.keys())
                vals = ",".join(["?" for _ in row.keys()])
                con.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals})", list(row.values()))
            con.commit()
            return len(data)
        finally:
            con.close()

db = ReadOnlyDuckDBConnection("/Users/kg/life-os-2026/data/warehouse/ons.duckdb")
