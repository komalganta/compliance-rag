import os, psycopg
from dotenv import load_dotenv
load_dotenv()
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    rows = conn.execute("select table_name from information_schema.tables where table_schema='public'").fetchall()
    print(rows)