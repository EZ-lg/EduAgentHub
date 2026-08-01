# 教培智能体 - AI 开发指南

## 项目简介

教培行业智能桌面工具，以 **"AI 对话式采集 + 按学科管理"** 为核心模式：

```
建档 → 新建学科 → AI对话式采集 → 生成学情报告+课程规划 → 导出PDF → 报名
教学 → 录入成绩 → 成绩曲线 → AI分析 → 课程规划调整 → 循环
知识 → 上传资料 → 自动切片入库(ChromaDB) → AI引用(RAG) + 智能问答
```

详细需求：`需求文档与设计方案.md`

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | Python 3.11+ FastAPI | 异步、自动 API 文档 |
| ORM | SQLAlchemy 2.0 + SQLite | 单文件零配置，10张业务表 |
| 向量数据库 | ChromaDB 0.5 (嵌入式) | 知识库语义检索，无需独立服务 |
| AI 服务 | 适配器模式 | LLM + Embedding 均走 API，运行时切换 Provider |
| 文档解析 | python-docx / PyPDF2 / markdown | 知识库上传解析 |
| 前端框架 | Vue.js 3 CDN | `vue.global.prod.js`，无需 npm/build |
| 前端路由 | Vue Router 4 CDN | Hash 模式 `#/xxx`，无需服务端配置 |
| 图表 | ECharts 5 CDN | 成绩曲线图 |
| 样式 | Tailwind CSS CDN | 快速开发，也可手写 CSS |
| PDF 导出 | jsPDF + html2canvas (前端) | 浏览器自带中文字体，免折腾 |
| 打包 | PyInstaller 6 | 单 exe，约 300-800MB |

---

## 核心数据模型（重要！）

```
students (1) ──────< subjects (N)           ← 一个学生有多个学科
subjects (1) ──────< ai_conversations (N)   ← AI 对话记录
subjects (1) ──────< reports (N)            ← 学情报告
subjects (1) ──────< scores (N)             ← 考试成绩
subjects (1) ──────< course_plans (N)       ← 课程规划
subjects (1) ──────< communication_logs (N) ← 沟通日志
teachers ────────── (独立)
knowledge_docs ──── (独立)
settings ────────── (独立，key-value)
```

**关键**：报告、规划、成绩、日志都挂在 `subjects` 下，不是直接挂 `students` 下。

---

## 项目目录结构

```
tutoring-agent/
├── main.py                     # 入口：启动 FastAPI + 自动打开浏览器
├── requirements.txt
├── config.py                   # 全局配置（路径、数据库URL等）
│
├── backend/
│   ├── app.py                  # FastAPI 应用工厂
│   ├── routers/                # API 路由（每个模块一个文件）
│   │   ├── students.py
│   │   ├── subjects.py
│   │   ├── conversations.py
│   │   ├── reports.py
│   │   ├── scores.py
│   │   ├── course_plans.py
│   │   ├── communication_logs.py
│   │   ├── teachers.py
│   │   ├── knowledge_base.py
│   │   ├── settings.py
│   │   └── dashboard.py
│   ├── models/                 # SQLAlchemy 模型
│   │   ├── student.py
│   │   ├── subject.py
│   │   ├── ai_conversation.py
│   │   ├── report.py
│   │   ├── score.py
│   │   ├── course_plan.py
│   │   ├── communication_log.py
│   │   ├── teacher.py
│   │   ├── knowledge_doc.py
│   │   └── setting.py
│   ├── services/               # 业务逻辑层
│   │   ├── conversation_service.py
│   │   ├── report_generator.py
│   │   ├── course_planner.py
│   │   ├── score_analyzer.py
│   │   ├── kb_service.py
│   │   └── document_parser.py
│   ├── ai/                     # AI 服务层（多模型适配）
│   │   ├── base.py
│   │   ├── factory.py
│   │   ├── manager.py
│   │   ├── providers/
│   │   │   ├── openai_provider.py
│   │   │   ├── claude_provider.py
│   │   │   ├── qwen_provider.py
│   │   │   ├── deepseek_provider.py
│   │   │   └── custom_openai_provider.py
│   │   └── prompts/            # Prompt 模板
│   │       ├── conversation.txt
│   │       ├── conversation_end.txt
│   │       ├── report_generation.txt
│   │       ├── report_regenerate.txt
│   │       ├── course_planning.txt
│   │       ├── score_analysis.txt
│   │       ├── plan_adjustment.txt
│   │       ├── knowledge_qa.txt
│   │       └── system_prompt.txt
│   └── utils/
│       ├── export_pdf.py
│       └── helpers.py
│
├── frontend/                   # 纯静态，无构建
│   ├── index.html              # SPA 入口
│   ├── css/style.css
│   ├── js/
│   │   ├── app.js              # Vue 应用 + 路由 + 全局状态
│   │   ├── api.js              # fetch 封装，统一错误处理
│   │   └── utils.js
│   ├── pages/
│   │   ├── dashboard.html
│   │   ├── student_list.html
│   │   ├── student_detail.html
│   │   ├── conversation.html
│   │   ├── report.html
│   │   ├── teachers.html
│   │   ├── knowledge_base.html
│   │   ├── knowledge_qa.html
│   │   └── settings.html
│   ├── components/
│   │   ├── navbar.html
│   │   ├── student_card.html
│   │   ├── subject_card.html
│   │   └── ai_editor.html
│   └── vendor/                 # CDN 离线备用（打包前下载）
│       ├── vue.global.prod.js
│       ├── vue-router.global.prod.js
│       └── echarts.min.js
│
├── data/                       # 运行时数据（不打包进exe）
│   ├── tutoring.db             # SQLite 自动创建
│   ├── chroma_data/            # ChromaDB 自动创建
│   ├── uploads/                # 上传文档
│   └── exports/                # 导出 PDF
│
└── build/
    ├── icon.ico
    └── build.spec              # PyInstaller 配置
```

---

## 开发规则

### 通用
- **先 Web 后 EXE**：开发阶段 `python main.py` 浏览器调试，成熟后打包
- **每完成一个模块就立刻测试**，不要一次写完全部再测
- **API 前缀**：`/api/`
- **数据库路径**：`data/tutoring.db`（通过 config.py 管理，exe 运行时在 exe 同级目录）
- **文件上传路径**：`data/uploads/`
- **PDF 导出路径**：`data/exports/`

### 后端
- 路由文件在 `backend/routers/` 下，每个模块一个文件
- 业务逻辑在 `backend/services/` 下，不要在路由里写复杂逻辑
- 数据库操作通过 SQLAlchemy ORM，不要拼 SQL 字符串
- AI 调用统一通过 `AIManager` 单例，不要直接调 API
- 新增 Provider 只需在 `backend/ai/providers/` 下新增一个类
- Prompt 模板用 Jinja2 渲染，模板文件放在 `backend/ai/prompts/`
- 所有时间戳用 ISO 格式字符串存储
- API 返回格式统一：`{"success": true, "data": {...}}` 或 `{"success": false, "error": "..."}`

### 前端
- **不需要** Node.js、npm、webpack、vite
- Vue.js 3 通过 CDN 引入，全局变量 `Vue`
- Vue Router 4 通过 CDN 引入，全局变量 `VueRouter`
- Hash 路由：`#/dashboard`、`#/students`、`#/student/:id`、`#/conversation/:id` 等
- 页面模板通过 `fetch()` 加载 HTML 片段，缓存到内存
- 全局状态用 `reactive()` + `provide/inject`，不需要 Pinia
- API 调用统一走 `api.js` 封装的 `fetch`，返回 JSON
- 样式优先用 Tailwind CDN 的 class，复杂样式写 `style.css`

### 数据
- 学生 `status`：`active` | `completed` | `abandoned`
- 学科 `status`：`active` | `paused`
- JSON 字段：`answers_json`、`content_json`、`plan_json`、`messages_json`
- 删除学生 → 级联删除学科及所有关联数据 (ON DELETE CASCADE)
- **必须启用 SQLite 外键**：`backend/models/__init__.py` 里已加 `PRAGMA foreign_keys=ON`，所有表的新增 FK 级联都依赖它，改动 models 时不要移除
- 停用学科 ≠ 删除，数据全保留

### AI 配置
- LLM 和 Embedding 配置独立，存在 `settings` 表中
- key: `llm_config`，value_json: `{"provider": "openai", "api_key": "...", "base_url": "...", "model_name": "gpt-4o", "temperature": 0.7, "max_tokens": 4096, ...}`
- key: `embedding_config`，value_json: `{"provider": "openai", "api_key": "...", "base_url": "...", "model_name": "text-embedding-3-small", ...}`
- Provider 5 个：`openai` / `deepseek` / `claude` / `qwen` / `custom_openai`（后三者及自定义为 OpenAI 兼容协议）
- 通过 `backend/ai/manager.py` 的 `ai_manager` 单例获取 Provider，不要直接 new
- 新增 Provider：在 `backend/ai/providers/` 建类 → 在 `providers/__init__.py` 导入 → 在 `factory.py` 的 `PROVIDER_CLASSES` 登记
- AI 调用统一走 `AIManager`，配置变更后调用 `ai_manager.reload_config()`
- 设置页提供"测试连接"按钮，用当前表单配置测试（无需先保存）
- 切换 Embedding 需提示重建知识库

### 打包
- CDN 资源提前下载到 `frontend/vendor/`
- 入口 `main.py` 处理 `sys._MEIPASS` 判断是否在 exe 内运行
- data 目录放在 exe 同级，不打包进 exe
- 端口从 8888 开始自动寻找可用端口

---

## 当前进度

| 阶段 | 状态 | 内容 |
|------|------|------|
| P1 项目骨架 | ✅ 已完成 | FastAPI + SQLite建表 + 前端骨架 + 导航 |
| P2 AI 服务层 | ✅ 已完成 | BaseLLMProvider + Provider×5 + AIManager + 设置页AI配置 |
| P3 学生档案+学科 | ✅ 已完成 | 学生CRUD + 学科增删/停用 + 详情页 |
| P4 AI对话采集 | ⬜ 待开发 | 对话UI + 消息API + AI追问 + 结束判断 |
| P5 报告生成导出 | ⬜ 待开发 | Prompt模板 + 报告预览/编辑 + 重新生成 + PDF导出 |
| P6 成绩+规划 | ⬜ 待开发 | 成绩录入 + ECharts曲线 + AI分析 + 课程规划编辑器 |
| P7 教师+日志 | ⬜ 待开发 | 教师CRUD + 沟通日志CRUD |
| P8 知识库+问答 | ⬜ 待开发 | 上传/解析/入库 + 管理界面 + 智能问答 |
| P9 工作台+打包 | ⬜ 待开发 | 统计看板 + PyInstaller + 全流程测试 |

---

## 开发顺序

严格按照 P1 → P9 顺序：
1. P1-P2 是基础设施
2. P3 学生+学科是 P4 对话的前置
3. P4 对话完成后 P5 报告才有输入
4. P8 知识库完成前 P5 的 RAG 部分可先用空知识库跑通
5. P9 在 P2 后即可试打包验证 ChromaDB 兼容性

---

## 快速启动

```bash
pip install -r requirements.txt
venv/Scripts/activate   # 激活虚拟环境                                                                   
python main.py
# → 浏览器自动打开 http://127.0.0.1:8888
```

---

## 参考文件

- 完整需求：`需求文档与设计方案.md`
- 数据模型（第 5 节）：建表 SQL + JSON 结构 + 学科状态机
- API 设计（第 6 节）：30+ 接口 + 请求响应示例
- AI 架构（第 7 节）：适配器模式 + RAG 流程 + 10 个 Prompt 模板
- UI 原型（第 8 节）：布局 + 路由 + 关键页面 ASCII 稿
