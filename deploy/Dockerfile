# 教培智能体 — 服务器部署镜像（2.0 双轨形态之一）
# 用途：把同一套代码以"网站"形态部署到服务器
# 构建：docker build -f deploy/Dockerfile -t eduagent:2.0 .
# 运行：docker run -d -p 8888:8888 -v edu_data:/data eduagent:2.0
FROM python:3.11-slim

# ChromaDB/onnxruntime 需要的系统运行库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依赖层（利用 Docker 缓存，改代码不重装依赖）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码 + 前端静态资源（排除运行时数据与打包产物）
COPY backend ./backend
COPY frontend ./frontend
COPY config.py main.py build_tailwind.py ./
COPY requirements.txt ./

# 服务器形态：绑定 0.0.0.0，数据落到持久卷
ENV EDU_HOST=0.0.0.0 \
    EDU_PORT=8888 \
    EDU_DATA_DIR=/data \
    EDU_DATABASE_URL=sqlite:////data/tutoring.db \
    EDU_CHROMA_PATH=/data/chroma_data \
    EDU_FRONTEND_DIR=/app/frontend

VOLUME ["/data"]
EXPOSE 8888

# 服务器形态入口（非 exe；uvicorn 由依赖提供）
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8888"]
