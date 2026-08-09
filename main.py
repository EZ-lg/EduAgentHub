"""
教培智能体 - 入口文件
启动 FastAPI 服务 + 自动打开浏览器
"""
import webbrowser
import threading
import socket
import time
import uvicorn

from config import DEFAULT_PORT, HOST
# 强制导入 backend.app，确保 PyInstaller 收集整个 backend 包
# （下方 uvicorn.run 的 "backend.app:app" 是字符串，静态分析无法识别该依赖，不 import 打包后会缺 backend）
from backend.app import app  # noqa: F401


def find_free_port(start: int = DEFAULT_PORT) -> int:
    """自动查找可用端口"""
    port = start
    while port < start + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((HOST, port)) != 0:
                return port
        port += 1
    return start


def open_browser(url: str):
    """延迟打开浏览器"""
    time.sleep(1.5)
    webbrowser.open(url)


def main():
    port = find_free_port()
    url = f"http://{HOST}:{port}"
    print(f"教培智能体启动: {url}")
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    uvicorn.run("backend.app:app", host=HOST, port=port)


if __name__ == "__main__":
    main()
