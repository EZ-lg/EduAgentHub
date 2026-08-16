"""
2.0 冲突边界测试（P6b）

覆盖：
- Part A（纯函数，无需 DB）：教师/教室/学生跨班 三重冲突 + 批量冲突检测
- Part B（隔离临时库，走 API）：寒暑假班 vs 学期班冲突、两寒暑假班不重叠、续课冲突（新高一语文班 demo 场景）

运行：venv/Scripts/python.exe -m unittest backend.tests.test_conflicts -v
"""
import os
import shutil
import tempfile
import unittest

# ---- 隔离数据目录（必须在导入 backend 前设置）----
_TMP = tempfile.mkdtemp(prefix="edu_conf_")
os.environ["EDU_DATA_DIR"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.models import init_db  # noqa: E402
from backend.services.scheduler import check_conflict, check_conflicts_batch  # noqa: E402

# ============================================================ Part A：纯函数冲突
class TestSchedulerConflicts(unittest.TestCase):
    def _item(self, **kw):
        base = {"class_id": 1, "weekday": 0, "start_time": "08:00", "end_time": "10:00",
                "classroom_id": 1, "teacher_id": 1, "student_ids": [1]}
        base.update(kw)
        return base

    def test_teacher_conflict(self):
        occupied = [self._item(class_id=1, classroom_id=1, teacher_id=1)]
        new = self._item(class_id=2, classroom_id=2, teacher_id=1, student_ids=[2])
        types = [c["type"] for c in check_conflict(occupied, new)]
        self.assertIn("teacher", types)
        self.assertNotIn("classroom", types)
        self.assertNotIn("student", types)

    def test_classroom_conflict(self):
        occupied = [self._item(class_id=1, classroom_id=1, teacher_id=1)]
        new = self._item(class_id=2, classroom_id=1, teacher_id=2, student_ids=[2])
        types = [c["type"] for c in check_conflict(occupied, new)]
        self.assertIn("classroom", types)
        self.assertNotIn("teacher", types)
        self.assertNotIn("student", types)

    def test_student_cross_class_conflict(self):
        """学生跨班：同一学生两门课同时段（不同教师/教室）→ 学生冲突"""
        occupied = [self._item(class_id=1, classroom_id=1, teacher_id=1, student_ids=[1, 9])]
        new = self._item(class_id=2, classroom_id=2, teacher_id=2, student_ids=[1, 8])
        types = [c["type"] for c in check_conflict(occupied, new)]
        self.assertIn("student", types)
        self.assertEqual(len(types), 1)  # 仅学生冲突，教室/教师不同不触发

    def test_no_conflict_on_different_time(self):
        occupied = [self._item(weekday=0, start_time="08:00", end_time="10:00")]
        new = self._item(class_id=2, weekday=0, start_time="10:10", end_time="12:10",
                         classroom_id=1, teacher_id=1, student_ids=[1])
        self.assertEqual(check_conflict(occupied, new), [])

    def test_batch_detects_multiple_conflicts(self):
        a = self._item(class_id=1, classroom_id=1, teacher_id=1, student_ids=[1])
        b = self._item(class_id=2, classroom_id=1, teacher_id=1, student_ids=[1])
        c = self._item(class_id=3, classroom_id=3, teacher_id=3, student_ids=[3],
                       weekday=1, start_time="14:00", end_time="16:00")
        conflicts = check_conflicts_batch([a, b, c])
        # a-b 同一教师+同一教室+同一学生 → 应有 3 类冲突（在 a vs b 上触发 2 次各带类型）
        types = {x["type"] for x in conflicts}
        self.assertEqual(types, {"classroom", "teacher", "student"})
        # c 不冲突，不应出现在 on_item 中
        on_items = {x["on_item"]["class_id"] for x in conflicts}
        self.assertNotIn(3, on_items)


# ============================================================ Part B：DB 场景（隔离库）
def _setup_basic(client):
    """建教师2/教室2/学生1，返回 (t1, t2, r1, r2, sid)"""
    t1 = client.post("/api/teachers", json={"name": "边界师A"}).json()["data"]["id"]
    t2 = client.post("/api/teachers", json={"name": "边界师B"}).json()["data"]["id"]
    t3 = client.post("/api/teachers", json={"name": "边界师C"}).json()["data"]["id"]
    r1 = client.post("/api/classrooms", json={"name": "边界室A", "capacity": 10}).json()["data"]["id"]
    r2 = client.post("/api/classrooms", json={"name": "边界室B", "capacity": 10}).json()["data"]["id"]
    sid = client.post("/api/students", json={"name": "边界学生"}).json()["data"]["id"]
    return t1, t2, t3, r1, r2, sid


class TestDBConflicts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP, ignore_errors=True)

    def test_summer_vs_semester_conflict(self):
        """寒暑假班建班撞学期班周一课 → 400 + conflicts"""
        c = self.client
        t1, t2, t3, r1, r2, sid = _setup_basic(c)
        # 学期班 + 周一 14:00 active 课
        cls_id = c.post("/api/classes", json={
            "name": "边界学期班", "subject_name": "数学", "teacher_id": t1,
            "classroom_id": r1, "class_type": "1vN", "term_type": "semester",
            "weekly_frequency": 1, "duration_minutes": 120, "student_ids": [sid]}).json()["data"]["id"]
        r = c.post("/api/schedules", json={
            "class_id": cls_id, "weekday": 0, "start_time": "14:00",
            "end_time": "16:00", "classroom_id": r1, "teacher_id": t1})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["data"]["created"])
        # 寒暑假班：2026-08-17 是周一，14:00 撞学期班 → 冲突
        r = c.post("/api/classes", json={
            "name": "边界暑假班", "subject_name": "数学", "teacher_id": t1,
            "classroom_id": r1, "class_type": "1vN", "term_type": "summer_winter",
            "start_date": "2026-08-17", "daily_start": "14:00", "daily_end": "16:00",
            "total_lessons": 5, "student_ids": [sid]})
        self.assertEqual(r.status_code, 400)
        detail = r.json().get("detail")
        self.assertIsInstance(detail, dict)
        self.assertIn("conflicts", detail)
        self.assertTrue(len(detail["conflicts"]) > 0)

    def test_two_summer_classes_non_overlap_ok(self):
        """两个寒暑假班时间不重叠 → 各自建班成功（同教师同教室不同班期）"""
        c = self.client
        t1, t2, t3, r1, r2, sid = _setup_basic(c)
        c1 = c.post("/api/classes", json={
            "name": "暑期一", "subject_name": "数学", "teacher_id": t2, "classroom_id": r2,
            "class_type": "1vN", "term_type": "summer_winter",
            "start_date": "2026-08-17", "daily_start": "14:00", "daily_end": "16:00",
            "total_lessons": 2, "student_ids": [sid]}).json()
        self.assertTrue(c1["success"])
        c2 = c.post("/api/classes", json={
            "name": "暑期二", "subject_name": "英语", "teacher_id": t3, "classroom_id": r2,
            "class_type": "1vN", "term_type": "summer_winter",
            "start_date": "2026-08-20", "daily_start": "14:00", "daily_end": "16:00",
            "total_lessons": 2, "student_ids": [sid]}).json()
        self.assertTrue(c2["success"])

    def test_extend_conflict_rollback(self):
        """续课撞已占用教室时段 → extended:false + conflicts，且不落库（班期不变）"""
        c = self.client
        t1, t2, t3, r1, r2, sid = _setup_basic(c)
        c1 = c.post("/api/classes", json={
            "name": "暑期一", "subject_name": "数学", "teacher_id": t2, "classroom_id": r2,
            "class_type": "1vN", "term_type": "summer_winter",
            "start_date": "2026-08-17", "daily_start": "14:00", "daily_end": "16:00",
            "total_lessons": 2, "student_ids": [sid]}).json()
        id1 = c1["data"]["id"]
        end1_before = c1["data"]["end_date"]
        # 另一个班 8/20 起占同一教室同一时段
        c.post("/api/classes", json={
            "name": "暑期二", "subject_name": "英语", "teacher_id": t3, "classroom_id": r2,
            "class_type": "1vN", "term_type": "summer_winter",
            "start_date": "2026-08-20", "daily_start": "14:00", "daily_end": "16:00",
            "total_lessons": 2, "student_ids": [sid]})
        # 续课 6 天 → 新班期 8/17~8/24 撞 8/20 起的暑期二
        r = c.post(f"/api/classes/{id1}/extend", json={"new_total": 6})
        self.assertEqual(r.status_code, 200)
        data = r.json()["data"]
        self.assertFalse(data["extended"])
        self.assertTrue(data.get("conflicts"))
        # 验证未落库：班期不变
        fresh = c.get(f"/api/classes/{id1}").json()["data"]
        self.assertEqual(fresh["end_date"], end1_before)
        self.assertEqual(fresh["total_lessons"], 2)


if __name__ == "__main__":
    unittest.main()
