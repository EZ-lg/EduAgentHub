"""
演示数据种子脚本 — 清空业务数据后写入一套可验证全部功能的演示数据

用法（在项目根目录运行）：
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m backend.tests.seed_demo

安全设计：
- 运行前自动备份 data/tutoring.db → data/backups/pre-seed-<时间戳>.db
- 保留 settings 表（llm_config / embedding_config / org_defaults / org_name 等配置不动）
- 清空 15 张业务表 + chroma_data 向量库 + uploads 上传目录
- 只操作真实数据目录（config.DATA_DIR），绝不设置 EDU_DATA_DIR 临时目录

覆盖场景：
- 学生/学科/成绩/报告/课程规划/沟通日志（1.0 学习维度）
- 教室/班级(学期+寒暑假)/课次/班级学生（2.0 上课维度）
- 工作台总览：待排课班级（高二英语冲刺班）、今日有课、学生卡片流
- 续课冲突演示：新高一语文班 = 冲突占位班（4号课堂 14:00），续课新初三数学班必撞
"""
import json
import os
import shutil
import sqlite3
from datetime import datetime

# ===== 必须放在任何 backend import 之前：确认操作的是真实数据目录 =====
if os.getenv("EDU_DATA_DIR"):
    raise SystemExit("检测到 EDU_DATA_DIR 环境变量，seed 脚本只操作真实数据目录，已中止。")

import config
from backend.models import SessionLocal, init_db
from backend.services.term_schedule import compute_end_date

# ---------- 备份 ----------
BACKUP_DIR = os.path.join(config.DATA_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
backup_path = os.path.join(BACKUP_DIR, f"pre-seed-{ts}.db")
if os.path.exists(config.DB_PATH):
    shutil.copy2(config.DB_PATH, backup_path)
    print(f"[1/3] 已备份旧库 → {backup_path}")
else:
    print("[1/3] 无旧库，跳过备份")

# ---------- 清空 ----------
init_db()
db = SessionLocal()
from sqlalchemy import text

# 删除顺序按外键依赖（子表先删），保留 settings
DELETE_ORDER = [
    "class_schedules", "class_students", "classes", "classrooms",
    "reports", "course_plans", "ai_conversations", "scores",
    "communication_logs", "subjects", "students", "teachers",
    "knowledge_docs", "qa_history", "activity_logs",
]
for table in DELETE_ORDER:
    db.execute(text(f"DELETE FROM {table}"))
db.commit()
print("[2/3] 业务表已清空（settings 配置保留）")

# 清空向量库 + 上传目录
for d in (config.CHROMA_PATH, config.UPLOAD_DIR):
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
print("     ChromaDB 向量库 / uploads 已清空")

# ---------- 写入演示数据 ----------
from backend.models.student import Student
from backend.models.subject import Subject
from backend.models.teacher import Teacher
from backend.models.classroom import Classroom
from backend.models.class_ import Class
from backend.models.class_student import ClassStudent
from backend.models.class_schedule import ClassSchedule
from backend.models.report import Report
from backend.models.course_plan import CoursePlan
from backend.models.score import Score
from backend.models.communication_log import CommunicationLog
from backend.models.activity_log import ActivityLog
from backend.models.setting import Setting

NOW = datetime.now().isoformat()

def add(obj):
    db.add(obj)
    return obj

# ---- 教师 ----
t_zhang = add(Teacher(name="张建国", phone="13800001001", subjects=json.dumps(["数学", "物理"], ensure_ascii=False), intro="数学教研组长，10 年教龄，擅长中高考冲刺"))
t_li = add(Teacher(name="李慧敏", phone="13800001002", subjects=json.dumps(["英语"], ensure_ascii=False), intro="英语专业八级，8 年教龄，小升初/中考英语"))
t_wang = add(Teacher(name="王强", phone="13800001003", subjects=json.dumps(["数学"], ensure_ascii=False), intro="5 年教龄，擅长一对一补差提分"))
t_chen = add(Teacher(name="陈静", phone="13800001004", subjects=json.dumps(["语文"], ensure_ascii=False), intro="6 年教龄，阅读写作专项"))
t_liuyang = add(Teacher(name="刘洋", phone="13800001005", subjects=json.dumps(["物理", "化学"], ensure_ascii=False), intro="4 年教龄，物理实验教学"))
db.flush()

# ---- 教室 ----
rooms = {
    "评估室": 3, "VIP1": 2, "VIP2": 2, "VIP3": 2,
    "4号课堂": 15, "5号课堂": 12, "6号课堂": 20,
}
room_ids = {}
for name, cap in rooms.items():
    r = add(Classroom(name=name, capacity=cap, location="", notes="", status="active"))
    db.flush()  # autoflush=False，先 flush 才能拿到自增 id
    room_ids[name] = r.id

# ---- 学生 + 学科 ----
# (姓名, 性别, 年级, 学校, 状态, [学科...])
STUDENTS = [
    ("陈思敏", "女", "初三", "实验中学", "active", ["数学", "英语"]),
    ("张伟", "男", "高一", "中山市第一中学", "active", ["物理", "数学"]),
    ("李娜", "女", "高二", "华侨中学", "active", ["英语", "语文"]),
    ("王芳", "女", "初一", "市实验中学", "active", ["数学"]),
    ("刘畅", "男", "初二", "实验中学", "active", ["数学", "物理"]),
    ("赵磊", "男", "高三", "中山市第一中学", "active", ["数学"]),
    ("孙悦", "女", "六年级", "石岐中心小学", "active", ["英语"]),
    ("周航", "男", "初三", "博文中学", "active", ["数学"]),
    ("吴迪", "男", "高二", "华侨中学", "active", ["物理"]),
    ("郑好", "女", "新高一", "博文中学", "active", ["语文"]),
    ("何雨", "女", "六年级", "石岐中心小学", "active", ["英语"]),
]
stu = {}   # (学生名, 学科名) -> subject id
stu_id = {}  # 学生名 -> student id
for name, gender, grade, school, status, subjects in STUDENTS:
    s = add(Student(name=name, gender=gender, grade=grade, school=school, phone="1390000", parent_name="", parent_phone="", address="", source="转介绍", status=status, notes=""))
    db.flush()
    stu_id[name] = s.id
    for subj in subjects:
        sub = add(Subject(student_id=s.id, name=subj, status="active"))
        db.flush()
        stu[(name, subj)] = sub.id
db.flush()

# ---- 班级 ----
# (name, subject_key, teacher, room, class_type, term_type, weekly_frequency, total_lessons, daily_start, daily_end, start_date, end_date, notes)
def mk_class(name, subject_name, teacher, room, ctype="1vN", term="semester", freq=2, total=0, d_start="", d_end="", start="", end="", notes=""):
    c = add(Class(name=name, subject_id=None, subject_name=subject_name, teacher_id=teacher.id,
                  classroom_id=room_ids[room], class_type=ctype, term_type=term,
                  total_lessons=total, daily_start=d_start, daily_end=d_end,
                  weekly_frequency=freq, duration_minutes=120, start_date=start, end_date=end,
                  status="active", notes=notes))
    db.flush()
    return c

# 学期班
c_math2 = mk_class("初二数学冲刺班", "数学", t_zhang, "4号课堂", notes="每周两次，冲刺期末")
c_gao3_1v1 = mk_class("高三数学一对一", "数学", t_wang, "VIP2", ctype="1v1", notes="一对一拔高，目标 130+")
c_phy1 = mk_class("高一物理班", "物理", t_liuyang, "5号课堂", notes="力学专项")
c_eng2 = mk_class("高二英语冲刺班", "英语", t_li, "VIP3", notes="【待排课】语法+完形专项")
# 寒暑假班
c_sum_math = mk_class("新初三数学班", "数学", t_zhang, "4号课堂", term="summer_winter",
                      total=40, d_start="14:00", d_end="16:00", start="2026-07-15",
                      end=compute_end_date("2026-07-15", 40), notes="暑假集中冲刺，周日休息")
c_sum_phy = mk_class("新高二物理班", "物理", t_liuyang, "5号课堂", term="summer_winter",
                     total=12, d_start="16:10", d_end="18:10", start="2026-08-03",
                     end=compute_end_date("2026-08-03", 12), notes="假期预科")
c_sum_eng = mk_class("小升初英语班", "英语", t_li, "VIP3", term="summer_winter",
                     total=10, d_start="08:00", d_end="10:00", start="2026-08-10",
                     end=compute_end_date("2026-08-10", 10), notes="音标+基础语法")
# 冲突占位班：新初三数学班 8/29 结束后 8/30 起，同一教室 4号课堂 同一时段 14:00 → 续课数学班必撞
c_sum_yuwen = mk_class("新高一语文班", "语文", t_chen, "4号课堂", term="summer_winter",
                       total=10, d_start="14:00", d_end="16:00", start="2026-08-30",
                       end=compute_end_date("2026-08-30", 10), notes="预科阅读写作")

# ---- 班级学生 ----
# (class, [(学生名, 学科名)])
CLASS_MEMBERS = {
    c_math2.id: [("刘畅", "数学"), ("王芳", "数学"), ("周航", "数学")],
    c_gao3_1v1.id: [("赵磊", "数学")],
    c_phy1.id: [("张伟", "物理"), ("吴迪", "物理")],
    c_eng2.id: [("李娜", "英语"), ("陈思敏", "英语")],
    c_sum_math.id: [("周航", "数学"), ("王芳", "数学"), ("刘畅", "数学")],
    c_sum_phy.id: [("吴迪", "物理"), ("张伟", "物理")],
    c_sum_eng.id: [("孙悦", "英语"), ("何雨", "英语")],
    c_sum_yuwen.id: [("郑好", "语文")],
}
for cid, members in CLASS_MEMBERS.items():
    for sname, sname2 in members:
        db.flush()  # autoflush=False，先 flush 确保 class_students 可见
        db.add(ClassStudent(class_id=cid, student_id=stu_id[sname], subject_id=stu[(sname, sname2)], status="active"))
db.flush()

# ---- 已确认课次（学期班 active 周循环） ----
# (class, weekday(0=周一), start, end, room)
def mk_sched(c, weekday, start, end, room):
    db.add(ClassSchedule(class_id=c.id, weekday=weekday, start_time=start, end_time=end,
                         classroom_id=room_ids[room], teacher_id=c.teacher_id, status="active"))
mk_sched(c_math2, 0, "18:00", "20:00", "4号课堂")   # 周一
mk_sched(c_math2, 2, "18:00", "20:00", "4号课堂")   # 周三
mk_sched(c_gao3_1v1, 1, "19:00", "21:00", "VIP2")   # 周二
mk_sched(c_gao3_1v1, 5, "10:00", "12:00", "VIP2")   # 周六
mk_sched(c_phy1, 0, "20:00", "22:00", "5号课堂")    # 周一
mk_sched(c_phy1, 4, "20:00", "22:00", "5号课堂")    # 周五
# c_eng2 高二英语冲刺班：无课次 → 工作台「待排课」演示

# ---- 成绩 / 报告 / 课程规划 / 沟通日志 ----
def mk_scores(subject_id, rows):
    for exam, date, score, total in rows:
        db.add(Score(subject_id=subject_id, exam_name=exam, score=score, total_score=total,
                     exam_date=date, notes=""))

def report_json(title, subtitle, summary, chapters, plan, conclusion):
    return json.dumps({
        "title": title, "subtitle": subtitle, "summary": summary,
        "chapters": chapters, "plan": plan, "conclusion": conclusion,
        "kb_references": [],
    }, ensure_ascii=False)

def mk_report(subject_id, title, status, chapters, plan, conclusion="坚持执行计划，定期复盘。", summary=None):
    if not summary:
        summary = "方法总纲：先摸清当前薄弱点，再按节奏做专项突破；每次课后错题复盘，定期限时自测，稳步向目标分推进。"
    r = add(Report(subject_id=subject_id, conversation_id=None, title=title,
                   content_json=report_json(title, "", summary, chapters, plan, conclusion),
                   course_plan_id=None, kb_references_json="[]", status=status))
    db.flush()
    return r

def mk_plan(subject_id, rows, version=1, status="active", reason=""):
    p = add(CoursePlan(subject_id=subject_id, version=version, plan_json=json.dumps(rows, ensure_ascii=False),
                       status=status, adjustment_reason=reason))
    db.flush()
    return p

def plan_rows(teacher_name, teacher_id, n, subject="核心考点"):
    # 报告课程规划不写具体上课时间（由机构课表统一安排），只保留 课时/内容/课时数/教师
    return [{"lesson": f"第{i+1}课", "content": f"{subject}专题{i+1}",
             "hours": 1.5, "teacher_id": teacher_id, "teacher_name": teacher_name,
             "notes": ""} for i in range(n)]

def chapters_std(txts):
    titles = ["一、当前情况与目标", "二、目标达成路径", "三、核心战略",
              "六、本学科落地规划", "七、学期节奏与每周安排", "十、心态建设"]
    return [{"title": titles[i], "content": txts[i], "ai_generated": True, "last_modified": NOW}
            for i in range(len(txts))]

# 陈思敏/数学 —— 冲刺 600 分，报告 published，规划 v1(archived)+v2(active) 演示版本历史
sid = stu[("陈思敏", "数学")]
mk_scores(sid, [("初三期中", "2025-11-10", 92, 120), ("初三期末", "2026-01-20", 96, 120),
                ("初三一模", "2026-03-15", 85, 100), ("初三二模", "2026-04-20", 88, 100),
                ("中考模拟", "2026-05-25", 92, 100)])
mk_plan(sid, plan_rows("张建国", t_zhang.id, 8, "中考压轴"), version=1, status="archived", reason="")
mk_plan(sid, plan_rows("张建国", t_zhang.id, 10, "中考冲刺"), version=2, status="active", reason="一模后加大压轴题训练")
r1 = mk_report(sid, "陈思敏 · 数学 冲刺600分学情报告", "published",
               chapters_std(["基础扎实但压轴题失分多，目标中考 115+/120。",
                             "第一阶段补函数与几何综合，第二阶段限时套卷训练。",
                             "每周 2 次课，作业错题复盘。",
                             "详见下方课程规划表。",
                             "课程按班期节奏推进，重点放在压轴题突破。",
                             "保持信心，错题即财富。"]),
               plan_rows("张建国", t_zhang.id, 10, "中考冲刺"))
db.flush()
r1.course_plan_id = db.query(CoursePlan).filter(CoursePlan.subject_id == sid, CoursePlan.status == "active").first().id
db.add(CommunicationLog(subject_id=sid, method="面谈", content="与家长沟通冲刺目标，确认每周加一次模拟考试。", log_time="2026-05-30T18:00"))

# 陈思敏/英语
sid = stu[("陈思敏", "英语")]
mk_scores(sid, [("初三期中", "2025-11-10", 90, 120), ("初三期末", "2026-01-20", 95, 120), ("中考模拟", "2026-05-25", 98, 120)])

# 张伟/物理 —— 报告 published + 规划 v1
sid = stu[("张伟", "物理")]
mk_scores(sid, [("高一期中", "2025-11-12", 75, 100), ("高一月考", "2026-01-10", 80, 100),
                ("高一期末", "2026-01-25", 82, 100), ("高一期末2", "2026-06-20", 85, 100)])
mk_plan(sid, plan_rows("刘洋", t_liuyang.id, 8, "力学专项"), version=1)
mk_report(sid, "张伟 · 物理 力学拔高学情报告", "published",
          chapters_std(["力学概念清楚，综合大题建模较弱。", "两阶段：力与运动 → 功与能量。", "受力分析规范训练。", "见下方规划表。", "按班期推进，力学专项为主。", "多画受力图。"]),
          plan_rows("刘洋", t_liuyang.id, 8, "力学专项"))

# 张伟/数学
sid = stu[("张伟", "数学")]
mk_scores(sid, [("高一期中", "2025-11-12", 78, 100), ("高一期末", "2026-01-25", 82, 100), ("高一月考", "2026-04-10", 80, 100)])

# 李娜/英语 —— 报告 draft + 规划 v1 + 沟通日志
sid = stu[("李娜", "英语")]
mk_scores(sid, [("高二期中", "2025-11-15", 88, 150), ("高二期末", "2026-01-28", 95, 150),
                ("高二月考", "2026-03-10", 100, 150), ("高二期中2", "2026-05-12", 108, 150)])
mk_plan(sid, plan_rows("李慧敏", t_li.id, 6, "语法专项"), version=1)
mk_report(sid, "李娜 · 英语 语法完形专项", "draft",
          chapters_std(["词汇量足够，从句与虚拟语气薄弱。", "先语法后完形刷题。", "错题本复盘。", "见下方规划表。", "课程集中在周末推进。", "每日背 20 词。"]),
          plan_rows("李慧敏", t_li.id, 6, "语法专项"))
db.add(CommunicationLog(subject_id=sid, method="微信", content="反馈本周完形正确率提升明显，家长表示满意。", log_time="2026-05-15T20:00"))

# 李娜/语文
sid = stu[("李娜", "语文")]
mk_scores(sid, [("高二期中", "2025-11-15", 95, 150), ("高二期末", "2026-01-28", 102, 150), ("高二月考", "2026-04-10", 100, 150)])

# 王芳/数学
sid = stu[("王芳", "数学")]
mk_scores(sid, [("初一期中", "2025-11-15", 85, 120), ("初一期末", "2026-01-25", 90, 120), ("初一月考", "2026-05-10", 95, 120)])

# 刘畅/数学 —— 报告 published + 规划 v1
sid = stu[("刘畅", "数学")]
mk_scores(sid, [("初二期中", "2025-11-18", 80, 120), ("初二期末", "2026-01-22", 88, 120),
                ("初二月考", "2026-03-18", 90, 120), ("初二期中2", "2026-05-15", 92, 120),
                ("初二模拟", "2026-06-10", 95, 120)])
mk_plan(sid, plan_rows("张建国", t_zhang.id, 6, "函数与几何"), version=1)
mk_report(sid, "刘畅 · 数学 函数几何强化", "published",
          chapters_std(["一次函数与全等几何得分不稳。", "函数图象 → 几何辅助线两阶段。", "每日一题训练。", "见下方规划表。", "课程按班期节奏推进。", "坚持做题复盘。"]),
          plan_rows("张建国", t_zhang.id, 6, "函数与几何"))

# 刘畅/物理
sid = stu[("刘畅", "物理")]
mk_scores(sid, [("初二期中", "2025-11-18", 78, 100), ("初二期末", "2026-01-22", 82, 100), ("初二月考", "2026-04-10", 85, 100)])

# 赵磊/数学（一对一）—— 6 次成绩，报告 published，规划 v1(archived)+v2(active)
sid = stu[("赵磊", "数学")]
mk_scores(sid, [("高三摸底", "2025-09-10", 102, 150), ("高三期中", "2025-11-15", 110, 150),
                ("高三一模", "2026-01-15", 115, 150), ("高三二模", "2026-03-20", 120, 150),
                ("高三三模", "2026-04-25", 124, 150), ("高考模拟", "2026-05-30", 128, 150)])
mk_plan(sid, plan_rows("王强", t_wang.id, 8, "导数压轴"), version=1, status="archived", reason="")
mk_plan(sid, plan_rows("王强", t_wang.id, 10, "圆锥曲线压轴"), version=2, status="active", reason="二模后转向圆锥曲线")
mk_report(sid, "赵磊 · 数学 一对一冲刺130+", "published",
          chapters_std(["选填稳定，压轴题最后一问失分。", "导数 → 圆锥曲线两阶段攻坚。", "限时训练压轴题。", "见下方规划表。", "课程集中在周末推进。", "目标 130+。"]),
          plan_rows("王强", t_wang.id, 10, "圆锥曲线压轴"))
db.add(CommunicationLog(subject_id=sid, method="电话", content="确认二模后调整为一对一压轴题专项。", log_time="2026-03-22T15:00"))

# 孙悦/英语（小升初）—— 报告 published + 规划 v1
sid = stu[("孙悦", "英语")]
mk_scores(sid, [("六年级期中", "2025-11-12", 88, 100), ("六年级期末", "2026-01-20", 90, 100),
                ("小升初模拟一", "2026-04-18", 92, 100), ("小升初模拟二", "2026-05-25", 95, 100)])
mk_plan(sid, plan_rows("李慧敏", t_li.id, 6, "音标+基础语法"), version=1)
mk_report(sid, "孙悦 · 英语 小升初衔接", "published",
          chapters_std(["口语听力较好，拼写与语法不牢。", "音标 → 基础语法两阶段。", "每日朗读打卡。", "见下方规划表。", "暑假集中连续推进。", "快乐学习。"]),
          plan_rows("李慧敏", t_li.id, 6, "音标+基础语法"))

# 何雨/英语
sid = stu[("何雨", "英语")]
mk_scores(sid, [("六年级期中", "2025-11-12", 82, 100), ("六年级期末", "2026-01-20", 85, 100), ("小升初模拟一", "2026-04-18", 88, 100)])

# 周航/数学 —— 报告 published + 规划 v1
sid = stu[("周航", "数学")]
mk_scores(sid, [("初二期末", "2026-01-20", 70, 120), ("初三摸底", "2026-02-20", 75, 120),
                ("初三月考", "2026-04-10", 78, 120), ("初三期中", "2026-05-15", 82, 120)])
mk_plan(sid, plan_rows("张建国", t_zhang.id, 6, "暑假基础+压轴入门"), version=1)
mk_report(sid, "周航 · 数学 暑假冲刺班", "published",
          chapters_std(["基础题丢分较多，计算不稳。", "先基础后压轴入门。", "每日计算训练。", "见下方规划表。", "暑假集中连续推进。", "打好基础最重要。"]),
          plan_rows("张建国", t_zhang.id, 6, "暑假基础+压轴入门"))

# 吴迪/物理 —— 报告 draft + 规划 v1
sid = stu[("吴迪", "物理")]
mk_scores(sid, [("高二期中", "2025-11-15", 80, 100), ("高二期末", "2026-01-28", 85, 100),
                ("高二月考", "2026-03-10", 82, 100), ("高二期中2", "2026-05-12", 88, 100)])
mk_plan(sid, plan_rows("刘洋", t_liuyang.id, 6, "电磁学预科"), version=1)
mk_report(sid, "吴迪 · 物理 电磁学预科", "draft",
          chapters_std(["力学基础不错，电磁学未系统学过。", "电场 → 磁场预科。", "暑期预科衔接。", "见下方规划表。", "暑假集中连续推进。", "保持兴趣。"]),
          plan_rows("刘洋", t_liuyang.id, 6, "电磁学预科"))

# 郑好/语文
sid = stu[("郑好", "语文")]
mk_scores(sid, [("中考模拟", "2026-04-20", 105, 150), ("中考", "2026-06-22", 112, 150), ("高一摸底", "2026-08-10", 100, 150)])

# ---- 初始活动日志（供工作台「最近活动」展示）----
for act in [
    ("创建学生", "批量建档 11 名学生", None, None),
    ("生成学情报告", "陈思敏 数学 冲刺600分", stu_id["陈思敏"], stu[("陈思敏", "数学")]),
    ("生成学情报告", "赵磊 数学 一对一冲刺130+", stu_id["赵磊"], stu[("赵磊", "数学")]),
    ("创建班级", "新初三数学班（寒暑假班）", None, None),
    ("录入成绩", "孙悦 小升初模拟二 95分", stu_id["孙悦"], stu[("孙悦", "英语")]),
]:
    db.add(ActivityLog(action=act[0], detail=act[1], student_id=act[2], subject_id=act[3]))

# ---- 节次模板（保证智能排课可用，默认 5 时段）----
periods = [
    {"label": "上午①", "start": "08:00", "end": "10:00"},
    {"label": "上午②", "start": "10:10", "end": "12:10"},
    {"label": "下午①", "start": "14:00", "end": "16:00"},
    {"label": "下午②", "start": "16:10", "end": "18:10"},
    {"label": "晚自习", "start": "19:00", "end": "21:00"},
]
row = db.query(Setting).filter(Setting.key == "class_periods").first()
if not row:
    row = Setting(key="class_periods")
    db.add(row)
row.value_json = json.dumps(periods, ensure_ascii=False)

db.commit()
db.close()

# ---------- 汇总 ----------
import sqlite3 as _sqlite
con = _sqlite.connect(config.DB_PATH)
con.row_factory = _sqlite.Row
counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
          for t in ["students", "subjects", "teachers", "classrooms", "classes",
                    "class_students", "class_schedules", "reports", "scores",
                    "course_plans", "communication_logs", "activity_logs"]}
con.close()
print("\n[3/3] 演示数据写入完成 ✅")
print(f"     教师 {counts['teachers']} · 教室 {counts['classrooms']} · 学生 {counts['students']} · 学科 {counts['subjects']}")
print(f"     班级 {counts['classes']} · 班级学生 {counts['class_students']} · 已确认课次 {counts['class_schedules']}")
print(f"     报告 {counts['reports']} · 成绩 {counts['scores']} · 规划 {counts['course_plans']} · 沟通日志 {counts['communication_logs']}")
print("\n演示场景速览：")
print("  · 工作台「待排课」→ 高二英语冲刺班（无课次），可试智能排课")
print("  · 班级「新初三数学班」续课 → 撞「新高一语文班」(4号课堂 14:00) → 冲突弹窗不落库")
print("  · 学生总览学科卡含成绩迷你线 / 报告徽章 / 规划进度；工作台可钻取")
