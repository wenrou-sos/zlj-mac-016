"""本地传感器数据模拟器：生成温湿度、光照、土壤湿度数据，并按阈值产生告警"""
import math
import random
from datetime import datetime

from database import get_conn

# 各指标正常范围阈值 (min, max)；超出即告警
THRESHOLDS = {
    "temperature": (15.0, 32.0),    # ℃
    "humidity": (40.0, 85.0),       # %
    "soil_moisture": (20.0, 60.0),  # %
    "light": (2000.0, 80000.0),     # lux（仅白天 6:00-20:00 检查）
}

METRIC_NAMES = {
    "temperature": "温度",
    "humidity": "空气湿度",
    "soil_moisture": "土壤湿度",
    "light": "光照",
}

METRIC_UNITS = {
    "temperature": "℃",
    "humidity": "%",
    "soil_moisture": "%",
    "light": "lux",
}


def _diurnal(hour: float) -> float:
    """0~1 的昼夜曲线，14 点左右为峰值"""
    return max(0.0, math.sin(math.pi * (hour - 6) / 14)) if 6 <= hour <= 20 else 0.0


def generate_reading(greenhouse_id: int) -> dict:
    """模拟一次传感器读数：昼夜基准 + 棚间差异 + 随机游走 + 偶发异常"""
    now = datetime.now()
    day_factor = _diurnal(now.hour + now.minute / 60)
    gh_offset = (greenhouse_id - 2) * 0.8  # 不同大棚略有差异

    temperature = 18 + 12 * day_factor + gh_offset + random.gauss(0, 0.8)
    humidity = 75 - 25 * day_factor + random.gauss(0, 2)
    light = 55000 * day_factor * random.uniform(0.7, 1.1)
    soil_moisture = 42 + random.gauss(0, 3)

    # 约 3% 概率模拟一次异常，用于演示告警
    if random.random() < 0.03:
        metric = random.choice(["temperature", "humidity", "soil_moisture"])
        if metric == "temperature":
            temperature += random.choice([-1, 1]) * random.uniform(8, 14)
        elif metric == "humidity":
            humidity += random.choice([-1, 1]) * random.uniform(25, 40)
        else:
            soil_moisture += random.choice([-1, 1]) * random.uniform(20, 30)

    return {
        "greenhouse_id": greenhouse_id,
        "temperature": round(temperature, 1),
        "humidity": round(min(100, max(0, humidity)), 1),
        "light": round(max(0, light), 0),
        "soil_moisture": round(min(100, max(0, soil_moisture)), 1),
    }


def check_thresholds(reading: dict) -> list[dict]:
    """检查读数是否越限，返回异常项列表"""
    problems = []
    hour = datetime.now().hour
    for metric, (lo, hi) in THRESHOLDS.items():
        if metric == "light" and not (6 <= hour < 20):
            continue  # 夜间不检查光照
        value = reading[metric]
        if value < lo or value > hi:
            direction = "过低" if value < lo else "过高"
            # 越限幅度超过 20% 视为严重
            span = hi - lo
            over = max(lo - value, value - hi)
            level = "critical" if over > span * 0.2 else "warning"
            problems.append({
                "metric": metric,
                "level": level,
                "value": value,
                "message": (
                    f"{METRIC_NAMES[metric]}{direction}：{value}{METRIC_UNITS[metric]}"
                    f"（正常范围 {lo}~{hi}{METRIC_UNITS[metric]}）"
                ),
            })
    return problems


def save_reading_and_alerts(reading: dict):
    """写入读数并维护告警：
    - 越限且已有活动告警：更新告警的数值/级别/信息（跟随最新读数）
    - 越限且上一周期该指标正常：新建告警（人工处理后若越限持续，不重复弹出）
    - 恢复正常：自动解除活动告警
    """
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO sensor_readings
               (greenhouse_id, temperature, humidity, light, soil_moisture)
               VALUES (?, ?, ?, ?, ?)""",
            (reading["greenhouse_id"], reading["temperature"], reading["humidity"],
             reading["light"], reading["soil_moisture"]),
        )
        reading_id = cur.lastrowid
        problems = {p["metric"]: p for p in check_thresholds(reading)}

        # 上一条读数的越限情况，用于判断是否为“新发生”的越限
        prev = conn.execute(
            """SELECT * FROM sensor_readings
               WHERE greenhouse_id=? AND id<? ORDER BY id DESC LIMIT 1""",
            (reading["greenhouse_id"], reading_id),
        ).fetchone()
        prev_metrics = (
            {p["metric"] for p in check_thresholds(dict(prev))} if prev else set()
        )

        for metric in THRESHOLDS:
            active = conn.execute(
                """SELECT id FROM alerts
                   WHERE greenhouse_id=? AND metric=? AND status='active'""",
                (reading["greenhouse_id"], metric),
            ).fetchone()
            if metric in problems:
                p = problems[metric]
                if active:
                    # 读数恶化/好转时同步更新进行中的告警
                    conn.execute(
                        "UPDATE alerts SET level=?, message=?, value=? WHERE id=?",
                        (p["level"], p["message"], p["value"], active["id"]),
                    )
                elif metric not in prev_metrics:
                    conn.execute(
                        """INSERT INTO alerts (greenhouse_id, metric, level, message, value)
                           VALUES (?, ?, ?, ?, ?)""",
                        (reading["greenhouse_id"], metric, p["level"], p["message"], p["value"]),
                    )
            elif active:
                conn.execute(
                    """UPDATE alerts SET status='resolved',
                       resolved_at=datetime('now', 'localtime') WHERE id=?""",
                    (active["id"],),
                )
        conn.commit()
    finally:
        conn.close()


def simulate_once():
    """对所有大棚采集一轮数据"""
    conn = get_conn()
    try:
        ids = [r["id"] for r in conn.execute("SELECT id FROM greenhouses")]
    finally:
        conn.close()
    for gh_id in ids:
        save_reading_and_alerts(generate_reading(gh_id))
