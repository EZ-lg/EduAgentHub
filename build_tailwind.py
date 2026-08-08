# -*- coding: utf-8 -*-
"""编译 Tailwind 为本地静态 CSS（解决 CDN 在部分网络不可用导致的排版崩溃）。

用法：
    python build_tailwind.py            # 编译 + 压缩 → frontend/vendor/tailwind.css
    python build_tailwind.py --no-minify # 不压缩（便于调试/查看类是否命中）

何时需要重跑（纪律，见 CLAUDE.md）：
    - 新增了 Tailwind 工具类（class 名），且该 class 之前没编译进 CSS
    - 新增了页面/组件 HTML 或 JS 里用了新的 class
    - 升级 Tailwind 版本后

注意：CSS 是"构建时编译"产物，改动 class 后忘记重跑，
新增的 class 会静默无样式（排版会"看起来正常但细节丢失"）。
"""
import subprocess
import sys
from pathlib import Path

# Windows 控制台默认 GBK，统一成 UTF-8，避免 emoji/中文输出乱码或抛 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
INPUT_CSS = ROOT / "build" / "tailwind-input.css"
OUTPUT_CSS = ROOT / "frontend" / "vendor" / "tailwind.css"
CONTENT_GLOB = "./frontend/**/*.{html,js}"

# 优先用 standalone 单文件 exe（无需 Node）；否则用 npm 装的 JS CLI（build/tools）
STANDALONE_EXE = ROOT / "build" / "tools" / "tailwindcss.exe"
NPM_CLI = ROOT / "build" / "tools" / "node_modules" / "tailwindcss" / "lib" / "cli.js"


def resolve_cli():
    if STANDALONE_EXE.exists():
        return ["str", str(STANDALONE_EXE)]  # 直接执行 exe
    if NPM_CLI.exists():
        return ["node", str(NPM_CLI)]
    return None


def main():
    minify = "--no-minify" not in sys.argv
    cli = resolve_cli()
    if cli is None:
        print(
            "[build_tailwind] 找不到 Tailwind CLI。请先执行以下任一方式安装：\n"
            "  方式A(推荐，无需Node)：从 GitHub Releases 下载 tailwindcss-windows-x64.exe 放到 build/tools/tailwindcss.exe\n"
            "  方式B(需要Node)：npm install --prefix build/tools tailwindcss@3.4.17 --registry=https://registry.npmmirror.com"
        )
        sys.exit(1)

    cmd = cli + ["-i", str(INPUT_CSS), "-o", str(OUTPUT_CSS),
                 "--content", CONTENT_GLOB] + (["--minify"] if minify else [])
    print("[build_tailwind] 执行:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        print("[build_tailwind] [FAIL] 编译失败")
        sys.exit(r.returncode)

    size = OUTPUT_CSS.stat().st_size if OUTPUT_CSS.exists() else 0
    print(f"[build_tailwind] [OK] 已生成 {OUTPUT_CSS.relative_to(ROOT)} ({size/1024:.1f} KB)"
          + ("" if minify else "（未压缩）"))
    print("[build_tailwind] 提示：index.html 引用本文件的版本号 ?v= 需与 APP_VERSION 同步递增")


if __name__ == "__main__":
    main()