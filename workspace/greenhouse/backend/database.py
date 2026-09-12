"""SQLite 数据库初始化与连接管理"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "greenhouse.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS greenhouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    crop TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1   -- 1 启用 / 0 停用（停用后不采集不告警，历史保留）
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    greenhouse_id INTEGER NOT NULL REFERENCES greenhouses(id),
    temperature REAL NOT NULL,      -- 温度 ℃
    humidity REAL NOT NULL,         -- 空气湿度 %
    light REAL NOT NULL,            -- 光照 lux
    soil_moisture REAL NOT NULL,    -- 土壤湿度 %
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_readings_gh_time
    ON sensor_readings(greenhouse_id, created_at);

CREATE TABLE IF NOT EXISTS irrigation_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    greenhouse_id INTEGER NOT NULL REFERENCES greenhouses(id),
    amount_l REAL NOT NULL,         -- 灌溉量（升）
    method TEXT NOT NULL DEFAULT '滴灌',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL CHECK (task_type IN ('fertilize', 'water', 'harvest')),
    title TEXT NOT NULL,
    greenhouse_id INTEGER NOT NULL REFERENCES greenhouses(id),
    planned_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'cancelled')),
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    greenhouse_id INTEGER NOT NULL REFERENCES greenhouses(id),
    metric TEXT NOT NULL,           -- temperature / humidity / light / soil_moisture
    level TEXT NOT NULL DEFAULT 'warning' CHECK (level IN ('warning', 'critical')),
    message TEXT NOT NULL,
    value REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved')),
    notified TEXT NOT NULL DEFAULT 'none' CHECK (notified IN ('none', 'sent', 'failed')),
    notify_error TEXT DEFAULT '',
    handler TEXT DEFAULT '',        -- 处理人
    handle_note TEXT DEFAULT '',    -- 处理备注/结论
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    resolved_at TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        # 兼容旧库：为 alerts 表补充通知与处理字段
        cols = {r[1] for r in conn.execute("PRAGMA table_info(alerts)")}
        for col, ddl in {
            "notified": "ALTER TABLE alerts ADD COLUMN notified TEXT NOT NULL DEFAULT 'none'",
            "notify_error": "ALTER TABLE alerts ADD COLUMN notify_error TEXT DEFAULT ''",
            "handler": "ALTER TABLE alerts ADD COLUMN handler TEXT DEFAULT ''",
            "handle_note": "ALTER TABLE alerts ADD COLUMN handle_note TEXT DEFAULT ''",
        }.items():
            if col not in cols:
                conn.execute(ddl)
        # 兼容旧库：greenhouses 增加启用状态
        gh_cols = {r[1] for r in conn.execute("PRAGMA table_info(greenhouses)")}
        if "active" not in gh_cols:
            conn.execute("ALTER TABLE greenhouses ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        # 首次运行写入默认大棚
        if conn.execute("SELECT COUNT(*) FROM greenhouses").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO greenhouses(name, crop) VALUES (?, ?)",
                [("1号棚", "番茄"), ("2号棚", "黄瓜"), ("3号棚", "草莓")],
            )
        conn.commit()
    finally:
        conn.close()
