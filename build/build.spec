# -*- mode: python ; coding: utf-8 -*-
"""教培智能体 - PyInstaller 打包配置（单 exe）

- 前端静态资源（frontend/ 含本地化的 Vue/Router/ECharts/jsPDF 等）→ _MEIPASS/frontend
- ChromaDB / onnxruntime 等动态加载包 → collect_all 收集子模块+数据+二进制
- data/ 运行数据（SQLite/ChromaDB/uploads/exports）在 exe 同级，不打包
"""
import os
import sys
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
# 关键包收集失败必须中止打包（静默吞掉会产出"启动即崩"的 exe）
CRITICAL_PKGS = {'chromadb', 'onnxruntime', 'fastapi', 'uvicorn', 'multipart'}
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
    except Exception as e:
        if pkg in CRITICAL_PKGS:
            print(f"[FATAL] collect_all({pkg}) 失败: {e}")
            sys.exit(1)
        print(f"[WARN] collect_all({pkg}) 失败，已跳过: {e}")

# 强制收集 backend 包全部子模块（uvicorn.run 用字符串引用 backend.app，静态分析收集不到）
try:
    backend_mods = collect_submodules('backend')
except Exception as e:
    print(f"[FATAL] collect_submodules('backend') 失败: {e}")
    sys.exit(1)
# 排除测试模块（backend.tests.*）：瘦身 + 减少打包噪音（构建不执行模块代码，无清库风险）
hiddenimports += [m for m in backend_mods if not m.startswith('backend.tests')]

# 断言 P0 数据可靠性关键模块已收集（漏打包 → windowed 下启动静默崩溃）
_REQUIRED_UTILS = {
    'backend.utils.db_health', 'backend.utils.migrate',
    'backend.utils.logging_setup', 'backend.utils.backup',
}
_missing = _REQUIRED_UTILS - set(hiddenimports)
if _missing:
    print(f"[FATAL] P0 关键模块未收集，打包必然运行崩溃: {sorted(_missing)}")
    sys.exit(1)

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
    icon=os.path.join(PROJECT_ROOT, 'build', 'icon.ico'),  # 商用品牌图标（多尺寸 ico）
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
