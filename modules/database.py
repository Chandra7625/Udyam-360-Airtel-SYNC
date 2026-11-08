import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import uuid
DB=Path(__file__).resolve().parents[1]/"data"/"orders.db"

def connect():
    DB.parent.mkdir(exist_ok=True)
    con=sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, business TEXT, bundle TEXT, monthly REAL, setup REAL, status TEXT, created TEXT)")
    con.commit(); return con

def create_order(business,bundle,monthly,setup):
    oid="UDY"+uuid.uuid4().hex[:8].upper(); con=connect()
    con.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?)",(oid,business,bundle,monthly,setup,"Order confirmed",datetime.now().isoformat(timespec='minutes')))
    con.commit(); con.close(); return oid

def get_orders():
    con=connect(); rows=con.execute("SELECT order_id,business,bundle,monthly,setup,status,created FROM orders ORDER BY created DESC").fetchall(); con.close(); return rows
