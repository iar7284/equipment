import pyodbc
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from config import Config

def _parse_server(raw: str):
    s = raw.strip()
    if s.lower().startswith("tcp:"):
        s = s[4:]
    host, port = (s.split(",", 1) + [""])[:2]
    return host.strip(), (port.strip() or "1433")

def make_engine():
    host, port = _parse_server(Config.DB_SERVER)
    odbc_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        f"Server={host},{port};"
        f"Database={Config.DB_NAME};"
        f"Uid={Config.DB_USER};"
        f"Pwd={Config.DB_PASSWORD};"
        "Encrypt=no;TrustServerCertificate=yes;Connection Timeout=30;"
    )
    return create_engine(
        "mssql+pyodbc:///?odbc_connect=" + quote_plus(odbc_str),
        fast_executemany=True,
        pool_pre_ping=True,
    )

ENGINE = make_engine()

def get_conn():
    return ENGINE.connect()
