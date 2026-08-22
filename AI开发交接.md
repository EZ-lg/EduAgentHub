# 教培智能体 — AI 开发者交接文档

> **给下一位 AI 开发者**：本文件让你**完全了解项目 + 无缝衔接后续开发**。它是「状态快照 + 操作手册 + 纪律清单」，配合以下文档一起读，即可像亲历过一样接手：
>
> 1. 本文件（`AI开发交接.md`）— 当前状态 + AI 工具链 + 最近操作记录
> 2. 根目录 `CLAUDE.md` — 项目简介/技术栈/开发规则（AI 每次会话自动加载）
> 3. 根目录 `2.0开发交接.md`（v2.0.3）— 2.0 权威交接（需求/决策/踩坑/代码结构）
> 4. `docs/2.0开发事项.md` — 2.0 完成记录（归档）
> 5. `docs/1.0开发事项.md` — 1.0 完整归档（继承的开发纪律 §七）
> 6. `需求文档与设计方案2.md` — 2.0 需求源头

---

## 一、当前状态快照（2026-08-16）

| 项 | 值 |
|----|----|
| **项目版本** | 2.0 全部完成（P1 → P6 后半），1.0（P1~P9）已归档 |
| **Git** | main 分支，最近 commit `9460b06`，已推送 origin/main，工作区干净 |
| **前端版本** | `APP_VERSION = '46'`（改前端后必须递增） |
| **UI 风格** | **紫色主题**（主色 `#6C5CE7`，仿 Dribbble EduRashi 仪表盘），浅色明亮 + 大圆角卡片 + 彩色统计卡 + 64px 图标栏 |
| **打包产物** | `dist/TutoringAgent2.0.exe`（71.9MB，windowed 无黑窗；用户已把 exe 命名为 2.0 版；dist/ 被 gitignore 不入库） |
| **数据库** | SQLite 16 张表，`data/tutoring.db`（**演示数据**：11 学生 / 5 教师 / 7 教室 / 10 班级 / 8 报告 / 57 成绩） |
| **回退基线** | tag `v2.0.2-pre-redesign`（指向 UI 改版前 `c4ceb9d`） |

**最近 3 个 commit**：
- `9460b06` docs(2.0): P6 后半完成 — exe 重打包 + 双轨验证 + 2.0 归档
- `6848b38` feat(UI): 前端全面改版 — 紫色主题 + 64px 图标栏 + 大圆角卡片 + 彩色统计卡
- `c4ceb9d` docs: 交接文档 v2.0.2

---

## 二、项目是什么

教培机构一站式**教务管理 + AI 助学**桌面工具。核心模式：

```
建档 → 新建学科 → AI对话式采集 → 生成学情报告+课程规划 → 导出PDF → 报名
教学 → 录入成绩 → 成绩曲线 → AI分析 → 课程规划调整 → 循环
知识 → 上传资料 → 自动切片入库(ChromaDB) → AI引用(RAG) + 智能问答
```

**1.0**（单人单科助学）：AI 对话采集 + 按学科管理，P1~P9 完成。
**2.0**（机构教务运营）：班级管理 + 智能排课 + 课表 + 全局总览 + 双轨部署，P1~P6 完成。
**部署双轨**：同一套代码，`dist/*.exe`（单机双击）↔ `uvicorn 0.0.0.0`（服务器网站），功能一致。

---

## 三、技术栈

| 层 | 技术 | 注意 |
|----|------|------|
| 后端 | Python 3.11+ FastAPI + SQLAlchemy 2.0 | 异步；SQLite（方言已抽象，理论可切 PG） |
| 向量库 | ChromaDB 0.5（嵌入式） | 知识库 RAG，无需独立服务 |
| AI | 适配器模式（Provider×5：openai/deepseek/claude/qwen/custom_openai） | 统一走 `AIManager` 单例 |
| 前端 | **Vue 3 CDN + Vue Router 4 Hash 路由，无 npm/build** | 纯静态，模板 fetch 加载 + 缓存 |
| 样式 | Tailwind（**本地编译** `build_tailwind.py`）+ 自定义 `style.css` 设计系统 | 新 class 必须重跑编译 |
| 图表 | ECharts 5 CDN | 成绩曲线 / 趋势图 |
| 导出 | jsPDF + html2canvas（前端） | PDF；Word 导出走后端 |
| 打包 | PyInstaller 6 单 exe | windowed 无黑窗 |

---

## 四、目录结构（关键）

```
tutoring-agent/
├── main.py                  # 入口：启动 FastAPI + 自动开浏览器（windowed 已处理 stdout=None）
├── config.py                # 配置（EDU_* 环境变量可覆盖）
├── build_tailwind.py        # 扫描 frontend 生成 vendor/tailwind.css
├── 2.0开发交接.md / AI开发交接.md / 测试流程.md
├── backend/
│   ├── app.py               # FastAPI 工厂
│   ├── routers/             # 每个模块一个路由文件（含 2.0：classrooms/classes/schedules/overview）
│   ├── services/            # 业务层（scheduler.py 排课算法 / term_schedule.py 寒暑假班 / report_generator.py）
│   ├── ai/                  # providers×5 + prompts/(.txt) + manager.py
│   ├── models/              # 16 表模型 + __init__.py（MIGRATION_RULES 迁移登记）
│   ├── utils/db.py          # 方言层（create_app_engine / run_light_migrations）
│   └── tests/               # regression.py(63项) / test_conflicts.py(8) / test_scheduler.py(7) / seed_demo.py
├── frontend/
│   ├── index.html           # SPA 入口（APP_VERSION + ?v= 版本机制）
│   ├── css/style.css        # ★ 设计系统（:root 变量 + 末尾 Tailwind 覆盖规则）★ 换肤主战场
│   ├── js/                  # app.js(路由) / api.js(fetch封装) / utils.js(showModal等)
│   ├── pages/               # 11 个页面（HTML + inline script，IIFE + Object.assign 导出）
│   ├── components/          # navbar.html(64px图标栏) / icons.html(SVG雪碧图)
│   └── vendor/              # 本地化库（Tailwind编译产物 / Vue / ECharts / jsPDF）
├── deploy/                  # Dockerfile / nginx.conf / deploy.md（服务器双轨）
├── data/                    # 运行时数据（SQLite/ChromaDB/uploads/exports/backups），不入库
└── docs/                    # 1.0开发事项.md / 2.0开发事项.md / 需求文档
```

---

## 五、核心数据模型（16 表，重点）

```
students (1) ──< subjects (N)           ← 学习维度：报告/规划/成绩/日志全挂这里
subjects ──< ai_conversations / reports / scores / course_plans / communication_logs
teachers / knowledge_docs / qa_history / settings / activity_logs  (独立)
classrooms  教室
classes     班级：subject_name(可空)+subject_id / teacher_id / classroom_id
            /class_type(1v1|1vN) / term_type(semester|summer_winter)
            /total_lessons / daily_start / daily_end / weekly_frequency
class_students  班级学生：唯一(class_id, student_id)，subject_id 可空
class_schedules 课次：weekday(0周一~6周日) / start_time / end_time / status(draft|active|archived)
```

**双维度铁律**：报告/规划/成绩/日志**永远挂 subjects**，不因班级引入而迁移到 classes。学科↔班级匹配：1v1 按 `class_students.subject_id`，1vN 按 `class.subject_name == subject.name`。

**学生 status**：`active|completed|abandoned`；学科 `active|paused`；班级 `active|paused`；课次 `draft|active|archived`。

---

## 六、AI 开发者专属工具链（重要！）

这些是之前会话验证过的方法，直接复用可大幅提速。

### 1. 识图（模型不能直接读图时）
```bash
node "C:/Users/hm/.claude/vision.js" "<图片路径>" "用中文描述这张图片"
node "C:/Users/hm/.claude/vision.js" --url "<图片链接>" "..."
python "C:/Users/hm/.claude/doc_vision.py" "<pdf/docx/pptx>"   # 文档识图
```

### 2. 前端语法检查（改动页面后必跑）
```bash
node -e "const fs=require('fs');const f=process.argv[1];const h=fs.readFileSync(f,'utf8');[...h.matchAll(/<script>([\s\S]*?)<\/script>/g)].forEach((s,i)=>{try{new Function(s[1]);console.log('OK',f)}catch(e){console.log('FAIL',f,e.message)}})" frontend/pages/xxx.html
```

### 3. CDP 验证（headless Edge 真实点击/截图/查 JS 错误）
```bash
# 启动 CDP Edge（保持后台）
"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu --remote-debugging-port=9225 --user-data-dir="<temp>/edge-profile" --window-size=1440,900 "about:blank" &
# Node 脚本连 WebSocket（Node≥22 有全局 WebSocket）：Page.navigate → Runtime.evaluate → Page.captureScreenshot
```
> 上一会话用此法验证过：13 路由巡检无 JS 错误、图标栏 hover 展开、空闲时段网格、弹窗、学生跳转等。

### 4. Tailwind 编译（新增 class / 新页后必跑）
```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe build_tailwind.py
```

### 5. 后端测试（改后端后必跑）
```bash
# 全量回归（63项，隔离库，绝不碰真实数据）
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m backend.tests.regression
# 冲突/排课单测
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m unittest backend.tests.test_conflicts backend.tests.test_scheduler -v
# 重建演示数据（备份→清空→写入，保留 settings）
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m backend.tests.seed_demo
```
> Windows 控制台 GBK，**所有打印中文的 Python 命令必须带 `PYTHONIOENCODING=utf-8`**。

### 6. 启动 / 服务器 / 打包
```bash
venv/Scripts/activate && python main.py           # 开发（自动开浏览器）
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m uvicorn backend.app:app --host 0.0.0.0 --port 8901  # 服务器模式
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m PyInstaller build/build.spec --noconfirm             # 打包（先确认 exe 未运行）
```

---

## 七、硬性纪律（务必遵守，都是踩过的坑）

1. **推送规则（用户明确要求）**：任何修改必须等用户实测验证通过后才 push git，不要提前推。除非用户在本轮明确说「弄完就提交推送」。
2. **改前端必递增 `APP_VERSION` + 同步 index.html 所有 `?v=`**（当前 46），否则用户浏览器加载旧模板。
3. **新增 Tailwind class / 新页面 → 跑 `build_tailwind.py`**，否则新 class 静默无样式。
4. **改前端颜色 → 优先改 `style.css` 的 `:root` CSS 变量**（全局生效）+ 末尾 Tailwind 覆盖规则（`.text-gray-*→var(--text)` 等）；**不要**在页面里写死 hex。已踩：全项目 385 处硬编码色类靠覆盖规则接管。
5. **回归/冲突测试用 `EDU_DATA_DIR` 临时库隔离**（先设环境变量再 import backend），**绝不碰 `data/tutoring.db`**。教训：曾误删真实学生「孟硕」。
6. **`SessionLocal` 是 `autoflush=False`**：先插入再查询前必须显式 `db.flush()`，否则查不到（寒暑假班冲突校验踩过）。
7. **排课只用确定性算法**（`scheduler.py`），LLM 只做点评不做求解。
8. **改课表/排课前必读 `2.0开发交接.md` §3.4 + §五.15~19**：归节次标准、冲突弹窗、showModal 条件字段、同路由不重挂载、排课流程现状。
9. **页面内联脚本必须 IIFE + 末尾 `Object.assign(window, {...})` 导出** onclick 引用的函数，否则点击无反应。
10. **API 400 返回 `{"detail":...}` 无 success 键**；业务"失败"尽量用 `success_response({...ok:false})`。前端 `API.request` 对非 2xx throw，冲突数据在 `err.detail.conflicts`。
11. **数据模型铁律**：报告/规划/成绩/日志挂 subjects。删学生会级联删全部（ON DELETE CASCADE，models/__init__ 已开 PRAGMA foreign_keys）。
12. **`data/tutoring.db` 是演示数据**（seed_demo 可一键重建，保留 settings），非真实业务。

---

## 八、最近的操作记录（2026-08-16，UI 改版 + 打包）

### 8.1 UI 全面改版（`6848b38`）
- **背景**：用户觉得旧前端（靛蓝 `#4f46e5` + 深色侧边栏）不美观，发来 Dribbble **EduRashi 教育仪表盘**要求模仿。
- **过程**：机构主题色先改橙（用户不满意）→ 恢复紫。最终**紫色主题**定稿。
- **落地**（关键改动都在 `frontend/css/style.css`）：
  - `:root`：主色 `#6C5CE7`、背景浅蓝灰渐变、圆角 10/16px、柔和阴影、侧边栏白底
  - 侧边栏：220px 深色 → **64px 纯图标栏**（`.sidebar:hover{width:200px}` + `.sidebar-label` opacity 切换，纯 CSS）
  - 统计卡：`.stat-card--blue/violet/pink/red/amber/green` 彩色浅底渐变 + 深色图标块
  - **末尾 Tailwind 覆盖规则**（`.text-gray-*`/`.text-indigo-*`/`.bg-*` → var）接管全项目硬编码色
  - 9 页批量替换 69 处旧靛蓝 hex → 紫色系/变量
  - 清除 5 处 emoji → SVG 线条图标
  - **修复 bug**：顶栏标题恒"工作台" → index.html 绑定 `{{ store.pageTitle }}`
- **验证**：headless Edge 截图 + vision.js 识图逐页核对；CDP 巡检 13 路由无 JS 错误；交互实测通过。

### 8.2 P6 后半收尾（`9460b06`）
- exe 重新打包 → `dist/TutoringAgent2.0.exe`（71.9MB，windowed）
- 模拟双击验证（CREATE_NO_WINDOW + 隔离临时库）：进程存活 + 端口 200 + 页面/API 正常
- 服务器双轨验证：127.0.0.1 + 局域网 IP 均 200
- 新增 `docs/2.0开发事项.md`，交接文档更新为 v2.0.3

### 8.3 过程中用过的验证资产（`C:/Users/hm/AppData/Local/Temp/ta-redesign/`，可复用作参考）
`recolor.js`（批量换色脚本）、`audit.js`（CDP 13 路由巡检）、`interact.js`（交互点击验证）、`shot.js`（CDP 截图）、`verify_exe.py`（exe 模拟双击验证）。均在临时目录，不在仓库。

---

## 九、后续候选任务（按价值排序，做之前先问用户拍板）

1. **教师可用时段表**（排课精度提升，当前取全部时段）— 涉及 scheduler.py + classes 表单
2. **课表周视图**（当前 P4 是单日网格）— 纯前端 schedule.html
3. **学生 Excel 导入 / 档案合并导出 / 报告风格设置**（1.0 遗留）
4. **服务器认证**：当前服务器模式**零认证**，仅限可信内网；上公网前必须加登录 + HTTPS
5. 新增 Provider / Prompt 模板：`backend/ai/providers/` + `prompts/`（含 schedule_eval.txt 排课点评）

> 任何新功能都要考虑**双轨约束**（exe + 服务器都能跑，别引入方言专属写法）。

---

## 十、如何无缝开始

```bash
cd E:/教培智能体
venv/Scripts/activate
python main.py            # → 浏览器自动开 http://127.0.0.1:8888
```
1. 先跑一遍 `python main.py` 看看当前效果
2. 读 `测试流程.md` 了解全功能清单
3. 有改动时：改 → 自测（§六工具链）→ 交用户实测 → 用户确认后再推送（§七.1）
4. 遇到不熟悉的模块先读 `2.0开发交接.md` 对应章节

**祝你无缝续接，顺利！🚀**
