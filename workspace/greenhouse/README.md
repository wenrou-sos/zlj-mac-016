# 大棚种植管理系统

记录大棚温湿度、光照与灌溉情况，安排施肥/浇水/采收任务，环境异常时自动告警提醒工作人员。

## 技术栈

- **后端**：FastAPI + SQLite（含本地传感器数据模拟器，每 10 秒采集一轮）
- **前端**：Vue 3（已本地化到 `frontend/static/`，无需联网、无需构建）

## 启动

```bash
pip install fastapi "uvicorn[standard]"
./run.sh          # 或 cd backend && python3 -m uvicorn main:app --port 8000
```

浏览器访问 http://localhost:8000

## 功能

| 模块 | 说明 |
|------|------|
| 环境概览 | 各大棚实时温度/湿度/光照/土壤湿度卡片，越限标红；历史趋势折线图 |
| 任务管理 | 安排施肥、浇水、采收任务，支持完成/取消 |
| 灌溉记录 | 记录灌溉量、方式（滴灌/喷灌/漫灌） |
| 告警中心 | 传感器越限自动生成告警（警告/严重两级），恢复后自动解除，也可人工标记处理 |

## 告警阈值（`backend/simulator.py` 中 `THRESHOLDS` 可调）

- 温度 15~32 ℃
- 空气湿度 40%~85%
- 土壤湿度 20%~60%
- 光照 2000~80000 lux（仅白天 6:00–20:00 检查）

模拟器约 3% 概率产生异常数据，便于演示告警流程。

## 目录结构

```
greenhouse/
├── backend/
│   ├── main.py        # FastAPI 应用与 API 路由
│   ├── database.py    # SQLite 建表与连接
│   ├── simulator.py   # 传感器模拟 + 阈值告警
│   └── greenhouse.db  # 数据库文件（首次运行自动创建）
├── frontend/
│   ├── index.html     # Vue 单页应用
│   └── static/vue.global.prod.js
└── run.sh
```

## 主要 API

- `GET /api/sensors/latest` 各大棚最新读数
- `GET /api/sensors/history?greenhouse_id=1&limit=60` 历史数据
- `GET/POST /api/tasks`，`PATCH /api/tasks/{id}` 任务管理
- `GET/POST /api/irrigation` 灌溉记录
- `GET /api/alerts`，`POST /api/alerts/{id}/resolve` 告警
- `GET /api/dashboard` 概览统计
