"""大棚种植管理系统 API 服务"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import get_conn, init_db
from simulator import simulate_once

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
SIMULATE_INTERVAL = 10  # 秒


async def simulator_loop():
    """后台任务：周期性模拟传感器采集"""
    while True:
        simulate_once()
        await asyncio.sleep(SIMULATE_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    simulate_once()  # 启动即采集一轮，避免首页无数据
    task = asyncio.create_task(simulator_loop())
    yield
    task.cancel()


app = FastAPI(title="大棚种植管理系统", lifespan=lifespan)


# ---------- 数据模型 ----------

class IrrigationIn(BaseModel):
    greenhouse_id: int
    amount_l: float = Field(gt=0)
    method: str = "滴灌"
    note: str = ""


class TaskIn(BaseModel):
    task_type: str = Field(pattern="^(fertilize|water|harvest)$")
    title: str
    greenhouse_id: int
    planned_date: str  # YYYY-MM-DD
    note: str = ""


class TaskUpdate(BaseModel):
    status: str = Field(pattern="^(pending|done|cancelled)$")


# ---------- 大棚与传感器 ----------

@app.get("/api/greenhouses")
def list_greenhouses():
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM greenhouses ORDER BY id")]
    finally:
        conn.close()


@app.get("/api/sensors/latest")
def latest_readings():
    """每个大棚最新一条读数"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT s.*, g.name AS greenhouse_name, g.crop
               FROM sensor_readings s
               JOIN greenhouses g ON g.id = s.greenhouse_id
               WHERE s.id IN (SELECT MAX(id) FROM sensor_readings GROUP BY greenhouse_id)
               ORDER BY s.greenhouse_id"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/sensors/history")
def sensor_history(greenhouse_id: int, limit: int = 60):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM sensor_readings WHERE greenhouse_id=?
               ORDER BY id DESC LIMIT ?""",
            (greenhouse_id, min(limit, 500)),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


# ---------- 灌溉记录 ----------

@app.get("/api/irrigation")
def list_irrigation(limit: int = 50):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT i.*, g.name AS greenhouse_name FROM irrigation_records i
               JOIN greenhouses g ON g.id = i.greenhouse_id
               ORDER BY i.id DESC LIMIT ?""",
            (min(limit, 200),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.post("/api/irrigation", status_code=201)
def add_irrigation(body: IrrigationIn):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO irrigation_records (greenhouse_id, amount_l, method, note) VALUES (?, ?, ?, ?)",
            (body.greenhouse_id, body.amount_l, body.method, body.note),
        )
        conn.commit()
        return {"id": cur.lastrowid}
    finally:
        conn.close()


# ---------- 任务管理 ----------

@app.get("/api/tasks")
def list_tasks(status: str | None = None):
    conn = get_conn()
    try:
        sql = """SELECT t.*, g.name AS greenhouse_name, g.crop FROM tasks t
                 JOIN greenhouses g ON g.id = t.greenhouse_id"""
        params: list = []
        if status:
            sql += " WHERE t.status=?"
            params.append(status)
        sql += " ORDER BY t.status='done', t.planned_date"
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


@app.post("/api/tasks", status_code=201)
def add_task(body: TaskIn):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO tasks (task_type, title, greenhouse_id, planned_date, note)
               VALUES (?, ?, ?, ?, ?)""",
            (body.task_type, body.title, body.greenhouse_id, body.planned_date, body.note),
        )
        conn.commit()
        return {"id": cur.lastrowid}
    finally:
        conn.close()


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: int, body: TaskUpdate):
    conn = get_conn()
    try:
        completed = "datetime('now', 'localtime')" if body.status == "done" else "NULL"
        cur = conn.execute(
            f"UPDATE tasks SET status=?, completed_at={completed} WHERE id=?",
            (body.status, task_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "任务不存在")
        return {"ok": True}
    finally:
        conn.close()


# ---------- 告警 ----------

@app.get("/api/alerts")
def list_alerts(status: str | None = None, limit: int = 100):
    conn = get_conn()
    try:
        sql = """SELECT a.*, g.name AS greenhouse_name FROM alerts a
                 JOIN greenhouses g ON g.id = a.greenhouse_id"""
        params: list = []
        if status:
            sql += " WHERE a.status=?"
            params.append(status)
        sql += " ORDER BY a.id DESC LIMIT ?"
        params.append(min(limit, 500))
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


@app.post("/api/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int):
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE alerts SET status='resolved',
               resolved_at=datetime('now', 'localtime')
               WHERE id=? AND status='active'""",
            (alert_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "告警不存在或已处理")
        return {"ok": True}
    finally:
        conn.close()


# ---------- 概览统计 ----------

@app.get("/api/dashboard")
def dashboard():
    conn = get_conn()
    try:
        return {
            "active_alerts": conn.execute(
                "SELECT COUNT(*) c FROM alerts WHERE status='active'").fetchone()["c"],
            "pending_tasks": conn.execute(
                "SELECT COUNT(*) c FROM tasks WHERE status='pending'").fetchone()["c"],
            "today_irrigation_l": conn.execute(
                """SELECT COALESCE(SUM(amount_l),0) s FROM irrigation_records
                   WHERE date(created_at)=date('now','localtime')""").fetchone()["s"],
            "readings_count": conn.execute(
                "SELECT COUNT(*) c FROM sensor_readings").fetchone()["c"],
        }
    finally:
        conn.close()


# ---------- 前端静态资源 ----------

@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
