"""
排课引擎单元测试
运行：venv/Scripts/python.exe -m unittest backend.tests.test_scheduler -v
"""
import unittest

from backend.services.scheduler import (
    auto_plan, check_conflict, check_conflicts_batch, schedule_to_weekly,
)

# 一周 5 天 × 2 个时段
def _slots(days=5, per_day=2):
    slots = []
    for d in range(days):
        for i in range(per_day):
            slots.append({"weekday": d, "start": f"{8 + i * 2:02d}:00", "end": f"{10 + i * 2:02d}:00", "label": f"D{d}-P{i}"})
    return slots


class TestConflict(unittest.TestCase):
    def test_classroom_conflict(self):
        occupied = [{"weekday": 0, "start_time": "08:00", "end_time": "10:00", "classroom_id": 1, "teacher_id": 1, "student_ids": [1], "class_id": 9}]
        new = {"weekday": 0, "start_time": "09:00", "end_time": "11:00", "classroom_id": 1, "teacher_id": 2, "student_ids": [2]}
        c = check_conflict(occupied, new)
        self.assertTrue(any(x["type"] == "classroom" for x in c))

    def test_teacher_conflict(self):
        occupied = [{"weekday": 1, "start_time": "08:00", "end_time": "10:00", "classroom_id": 1, "teacher_id": 7, "student_ids": [1]}]
        new = {"weekday": 1, "start_time": "08:00", "end_time": "10:00", "classroom_id": 2, "teacher_id": 7, "student_ids": [2]}
        c = check_conflict(occupied, new)
        self.assertTrue(any(x["type"] == "teacher" for x in c))

    def test_student_cross_class_conflict(self):
        occupied = [{"weekday": 2, "start_time": "10:00", "end_time": "12:00", "classroom_id": 1, "teacher_id": 1, "student_ids": [5, 6]}]
        new = {"weekday": 2, "start_time": "10:00", "end_time": "12:00", "classroom_id": 2, "teacher_id": 2, "student_ids": [5, 9]}
        c = check_conflict(occupied, new)
        self.assertTrue(any(x["type"] == "student" and x["student_ids"] == [5] for x in c))

    def test_no_conflict_different_time(self):
        occupied = [{"weekday": 0, "start_time": "08:00", "end_time": "10:00", "classroom_id": 1, "teacher_id": 1, "student_ids": [1]}]
        new = {"weekday": 0, "start_time": "10:00", "end_time": "12:00", "classroom_id": 1, "teacher_id": 1, "student_ids": [1]}
        self.assertEqual(check_conflict(occupied, new), [])

    def test_batch_no_internal_conflict_in_solution(self):
        """auto_plan 产出的方案内部必须零冲突"""
        classes = [
            {"id": 1, "name": "A", "class_type": "1vN", "teacher_id": 1, "classroom_id": 10, "student_ids": [1, 2], "weekly_frequency": 2},
            {"id": 2, "name": "B", "class_type": "1v1", "teacher_id": 2, "classroom_id": 10, "student_ids": [1], "weekly_frequency": 3},
        ]
        sols = auto_plan(classes, [], _slots(), num_solutions=3)
        self.assertTrue(sols, "应有候选方案")
        # 方案内部零冲突
        for sol in sols:
            items = [item for items in sol["plan"].values() for item in items]
            self.assertEqual(check_conflicts_batch(items), [], "方案内部应零冲突")
            # 每班次数满足
            for cls in classes:
                self.assertEqual(len(sol["plan"][cls["id"]]), cls["weekly_frequency"])

    def test_respects_existing_occupied(self):
        """已被占用的教室/教师/学生时段，新方案不得使用"""
        occupied = [{"weekday": 0, "start_time": "08:00", "end_time": "10:00",
                     "classroom_id": 10, "teacher_id": 1, "student_ids": [1], "status": "active", "class_id": 99}]
        classes = [
            {"id": 3, "name": "C", "class_type": "1v1", "teacher_id": 1, "classroom_id": 10, "student_ids": [1], "weekly_frequency": 1},
        ]
        sols = auto_plan(classes, occupied, _slots(), num_solutions=1)
        item = sols[0]["plan"][3][0]
        self.assertFalse(item["weekday"] == 0 and item["start_time"] == "08:00", "不得占用已被占用的时段")

    def test_weekly_view(self):
        weekly = schedule_to_weekly([
            {"weekday": 1, "start_time": "08:00", "end_time": "10:00"},
            {"weekday": 1, "start_time": "10:00", "end_time": "12:00"},
            {"weekday": 3, "start_time": "08:00", "end_time": "10:00"},
        ])
        self.assertEqual(len(weekly[1]), 2)
        self.assertEqual(len(weekly[3]), 1)
        self.assertEqual(weekly[1][0]["start_time"], "08:00")  # 时间排序


if __name__ == "__main__":
    unittest.main()
