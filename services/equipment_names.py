from typing import Dict, Tuple, List
from sqlalchemy import text
from flask import current_app
from db import get_conn
from config import Config

def _split_schema_object(qualified: str):
    q = qualified.strip().strip("[]")
    parts = q.split(".", 1)
    if len(parts) == 1:
        return "dbo", parts[0]
    return parts[0], parts[1]

def _quoted(schema: str, name: str) -> str:
    return f"[{schema}].[{name}]"

def _from_db() -> List[str]:
    schema, vname = _split_schema_object(Config.LIST_VIEW)
    view_fqn = _quoted(schema, vname)
    name_col = Config.IMG_NAMECOL

    sql = text(f"""
        SELECT DISTINCT CAST({name_col} AS NVARCHAR(4000)) AS name
        FROM {view_fqn}
        WHERE {name_col} IS NOT NULL
    """)
    with get_conn() as conn:
        return [r[0] for r in conn.execute(sql).fetchall()]

def _from_file() -> List[str]:
    p = Config.EQUIPMENT_NAMES_FILE
    try:
        with open(p, "r", encoding="utf-8") as f:
            names = [ln.strip() for ln in f if ln.strip()]
            # uniq while preserving order
            seen = set()
            out: List[str] = []
            for n in names:
                if n not in seen:
                    out.append(n)
                    seen.add(n)
            return out
    except FileNotFoundError:
        current_app.logger.warning("equipment_names.txt tidak ditemukan: %s", p)
        return []

def get_all_unit_names() -> Tuple[str, Dict[str, str]]:
    """
    Returns:
      source: 'db' | 'file'
      mapping: dict normalized_name -> canonical_name
    """
    try:
        names = _from_db()
        source = "db"
    except Exception:
        names = _from_file()
        source = "file"

    mapping = {n.strip().upper(): n.strip() for n in names}
    return source, mapping
