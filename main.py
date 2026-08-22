"""
教培智能体 - 入口文件
启动 FastAPI 服务 + 自动打开浏览器
"""
import os
import sys
import webbrowser
import threading
import socket
import time
import uvicorn

# PyInstaller windowed 模式（console=False，无黑窗）下 sys.stdout/sys.stderr 为 None，
# uvicorn 配置日志时访问 sys.stdout.isatty() 会抛 AttributeError 导致启动崩溃。
# 替换为 devnull 流，日志静默丢弃（windowed 应用没有控制台可写）。
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

from config import PORT, HOST, DATA_DIR
# 强制导入 backend.app，确保 PyInstaller 收集整个 backend 包
# （下方 uvicorn.run 的 "backend.app:app" 是字符串，静态分析无法识别该依赖，不 import 打包后会缺 backend）
from backend.app import app  # noqa: F401


def find_free_port(start: int = PORT) -> int:
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


def _block_start_if_data_failed():
    """启动护栏：db_health fatal 时留下 data/startup_failed.txt（数据库损坏且自动恢复失败），
    弹窗提示后退出，避免 windowed exe 只显示静默闪退、用户无从排查。

    弹窗前先复核 DB：若用户已手动恢复/替换回有效库，则清除标记正常放行，避免永久砖死。"""
    failed_txt = os.path.join(DATA_DIR, "startup_failed.txt")
    if not os.path.exists(failed_txt):
        return
    # 复核 DB 健康（用户可能已手动从 backups 恢复了）
    try:
        from backend.utils.db_health import check_db_integrity, clear_startup_failed
        res = check_db_integrity(deep=False)
        if res["error"] is None and res["quick_check"] == "ok":
            clear_startup_failed()
            return
    except Exception:
        pass
    try:
        with open(failed_txt, encoding="utf-8") as f:
            msg = f.read().strip() or "数据库损坏且自动恢复失败。"
    except OSError:
        msg = "数据库损坏且自动恢复失败，请从 data/backups/ 手动恢复。"
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "教培智能体：数据异常", 0x10)  # 0x10 = MB_ICONERROR
        except Exception:
            print(msg)
    sys.exit(1)


def main():
    _block_start_if_data_failed()
    port = find_free_port()
    url = f"http://{HOST}:{port}"
    print(f"教培智能体启动: {url}")
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    uvicorn.run("backend.app:app", host=HOST, port=port)


if __name__ == "__main__":
    main()
