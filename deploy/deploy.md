# 教培智能体 — 服务器部署指南（2.0 双轨形态）

> 本文件说明如何把**同一套代码**以"网站"形态部署到服务器。桌面形态（exe / `python main.py`）保持不变。
> 双轨原则：**代码零改动**，仅通过环境变量切换运行形态。

---

## 两种形态对比

| 形态 | 启动方式 | 绑定 | 数据位置 | 适用 |
|------|---------|------|---------|------|
| 桌面（1.0 默认） | `python main.py`（或 exe） | `127.0.0.1` 自动寻端口 | exe/项目同级 `data/` | 单机单用户 |
| **服务器（网站）** | `uvicorn backend.app:app` | `0.0.0.0:8888` | 环境变量 `EDU_DATA_DIR` 指定（持久卷） | 局域网 / 公网 |

---

## 一、直接运行（无 Docker）

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动（服务器形态）
```bash
export EDU_HOST=0.0.0.0        # 允许外部访问
export EDU_PORT=8888
export EDU_DATA_DIR=/srv/edu/data      # 数据持久目录（必设，别用默认）
# 可选：切 PostgreSQL（需先建库）——
# export EDU_DATABASE_URL=postgresql+psycopg2://user:pass@localhost/edu
python -m uvicorn backend.app:app --host $EDU_HOST --port $EDU_PORT
```

> 首次启动自动建表 + 轻量列迁移 + 自动备份，无需手工初始化。

### 3. 访问
`http://服务器IP:8888`

---

## 二、Docker 部署（推荐）

```bash
# 构建
docker build -f deploy/Dockerfile -t eduagent:2.0 .

# 运行（数据持久化到卷 edu_data）
docker run -d --name eduagent \
  -p 8888:8888 \
  -v edu_data:/data \
  eduagent:2.0

# 查看日志
docker logs -f eduagent
```

Dockerfile 已内置环境变量：绑定 `0.0.0.0`、数据在 `/data` 持久卷。备份文件也在 `/data/backups/` 内，随卷保留。

---

## 三、Nginx + HTTPS（公网发布）

1. 先以 `127.0.0.1:8888` 启动 uvicorn（改 `EDU_HOST=127.0.0.1`），或保持 Docker 内网映射。
2. 复制 `deploy/nginx.conf`，替换 `server_name` 与证书路径，启用 HTTPS。
3. 前端为纯静态 + Hash 路由，无需 rewrite；静态加速可直接由 Nginx 代理后端完成。

---

## 四、环境变量总表

| 变量 | 默认 | 说明 |
|------|------|------|
| `EDU_DATA_DIR` | `./data` | 数据目录（DB/Chroma/上传/导出/备份） |
| `EDU_DATABASE_URL` | `sqlite:///{DATA_DIR}/tutoring.db` | 数据库连接串（可切 PostgreSQL） |
| `EDU_CHROMA_PATH` | `{DATA_DIR}/chroma_data` | ChromaDB 向量库目录 |
| `EDU_FRONTEND_DIR` | 开发 `./frontend` | 前端静态目录 |
| `EDU_HOST` | `127.0.0.1` | 绑定主机（服务器设 `0.0.0.0`） |
| `EDU_PORT` | `8888` | 监听端口 |

---

## 五、注意事项（切库/公网化前必读）

- **登录/多用户**：当前为单机单用户设计，**无鉴权**。公网发布前需引入认证（2.0 已在 `backend/app.py` 预留中间件挂载位，规划中）。
- **SQLite 并发**：SQLite 适合单进程低并发。多用户公网场景建议切 PostgreSQL（ORM 已抽象方言，改 `EDU_DATABASE_URL` + 装对应驱动即可，`backend/utils/db.py` 已收敛差异）。
- **备份**：自动备份当前针对 SQLite（`backend/utils/backup.py`），切库后自动跳过，需另配数据库级备份。
- **CORS**：当前 `allow_origins=["*"]`，公网建议收紧为实际域名。
- **AI Key**：LLM/Embedding Key 存于 settings 表（数据库内），服务器部署请确保数据卷安全。
