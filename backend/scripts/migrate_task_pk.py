"""One-off migration: drop old research_tasks table (PK schema changed),
delete zombie RUNNING sessions left by crashed runs."""
import sqlite3

DB = r"d:\develop\python\trae\hello_agents\deepresearch-pro\data\deepresearch.db"

con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("DROP TABLE IF EXISTS research_tasks")
cur.execute("DELETE FROM research_sessions WHERE status = 'RUNNING'")
con.commit()
rows = cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print("tables now:", [r[0] for r in rows])
con.close()
