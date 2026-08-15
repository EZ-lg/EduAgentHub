# -*- mode: python ; coding: utf-8 -*-
"""教培智能体 - PyInstaller 打包配置（单 exe）

- 前端静态资源（frontend/ 含本地化的 Vue/Router/ECharts/jsPDF 等）→ _MEIPASS/frontend
- ChromaDB / onnxruntime 等动态加载包 → collect_all 收集子模块+数据+二进制
- data/ 运行数据（SQLite/ChromaDB/uploads/exports）在 exe 同级，不打包
"""
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# spec 在 build/ 下，脚本路径必须用绝对路径（相对 spec 目录解析会找不到 main.py）
PROJECT_ROOT = os.path.join(SPECPATH, '..')
MAIN_SCRIPT = os.path.join(PROJECT_ROOT, 'main.py')

# frontend 静态资源 + AI prompt 模板（.txt）都必须打包：
# prompt_loader 运行时从 _MEIPASS/backend/ai/prompts 读模板，漏打包会导致
# 打包版"测试连接通过但聊天/报告失败"（开发模式读源码目录所以正常）
datas = [
    (os.path.join(PROJECT_ROOT, 'frontend'), 'frontend'),
    (os.path.join(PROJECT_ROOT, 'backend', 'ai', 'prompts'), 'backend/ai/prompts'),
]
binaries = []
hiddenimports = []

# 动态加载/带数据文件的包：收集全部（子模块 + 数据 + 二进制）
for pkg in [
    'chromadb',           # 向量库：动态导入 + telemetry + 本地数据
    'onnxruntime',        # chromadb 默认 embedding 依赖
    'tokenizers',         # tokenizer 动态加载
    'huggingface_hub',    # 模型下载相关
    'posthog',            # chromadb telemetry
    'fastapi',
    'uvicorn',            # uvicorn 用 importlib 动态加载 loops/protocols
    'starlette',
    'multipart',
    'pydantic',
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass  # 个别包收集失败不阻塞

# 强制收集 backend 包全部子模块（uvicorn.run 用字符串引用 backend.app，静态分析收集不到）
try:
    hiddenimports += collect_submodules('backend')
except Exception:
    pass

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TutoringAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # 无黑窗（桌面工具）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
