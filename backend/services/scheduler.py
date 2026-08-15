"""
智能排课引擎 — 确定性约束求解（不依赖大模型）

设计原则：
- 纯函数、不查库（数据由路由组装后传入），便于单元测试
- 确定性：同一输入 → 同一输出（用 random.Random(seed) 局部随机，可复现）
- 硬约束（必须满足，保证零冲突）：
    H1 同教师同一时段 ≤ 1 课
    H2 同教室同一时段 ≤ 1 课
    H3 同学生同一时段 ≤ 1 课（跨班全局检查）
    H4 教室容量 ≥ 班级人数（由路由层校验教室 capacity）
- 软约束（评分启发，不阻断）：
    S1 学生同日多课时间隔 ≥ 30 分钟
    S2 教师单日负荷 ≤ 3 节
- 算法：班级按优先级排序 → 逐班贪心放置（槽位随机扰动产生多样候选）→ 评分 → Top-N

数据结构约定：
- class_schedule 课次：{class_id, weekday(0-6), start_time("HH:MM"), end_time("HH:MM"),
                          classroom_id, teacher_id, student_ids:[...], status}
- period_slots：[{weekday, start, end, label}]
"""
import random
from typing import List, Dict, Optional


def _to_min(t: str) -> int:
    """HH:MM → 分钟（用于区间判断）"""
    try:
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def _overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """两个时间区间是否重叠（[start,end) 左闭右开）"""
    return _to_min(a_start) < _to_min(b_end) and _to_min(b_start) < _to_min(a_end)


def check_conflict(occupied: List[dict], new_item: dict) -> List[dict]:
    """new_item 与 occupied 中所有课次检查冲突，返回冲突列表（空 = 无冲突）。

    冲突类型：classroom（教室占用）、teacher（教师占用）、student（学生跨班占用）
    """
    conflicts = []
    n_students = set(new_item.get("student_ids") or [])
    for o in occupied:
        if o.get("weekday") != new_item.get("weekday"):
            continue
        if not _overlaps(o.get("start_time", ""), o.get("end_time", ""),
                         new_item.get("start_time", ""), new_item.get("end_time", "")):
            continue
        # 教室冲突
        if (o.get("classroom_id") and new_item.get("classroom_id")
                and o["classroom_id"] == new_item["classroom_id"]):
            conflicts.append({
                "type": "classroom",
                "classroom_id": o["classroom_id"],
                "with_class_id": o.get("class_id"),
                "message": "教室在同一时段已被占用",
            })
        # 教师冲突
        if (o.get("teacher_id") and new_item.get("teacher_id")
                and o["teacher_id"] == new_item["teacher_id"]):
            conflicts.append({
                "type": "teacher",
                "teacher_id": o["teacher_id"],
                "with_class_id": o.get("class_id"),
                "message": "教师在同一时段已有课",
            })
        # 学生跨班冲突
        shared = n_students & set(o.get("student_ids") or [])
        if shared:
            conflicts.append({
                "type": "student",
                "student_ids": sorted(shared),
                "with_class_id": o.get("class_id"),
                "message": "学生同时在多个班上课",
            })
    return conflicts


def check_conflicts_batch(items: List[dict]) -> List[dict]:
    """检测整个课次列表内部的两两冲突（用于手动排课 / 确认前校验），返回全部冲突"""
    all_conflicts = []
    for i in range(len(items)):
        for c in check_conflict(items[:i], items[i]):
            c["on_item"] = {
                "class_id": items[i].get("class_id"),
                "weekday": items[i].get("weekday"),
                "start_time": items[i].get("start_time"),
                "end_time": items[i].get("end_time"),
            }
            all_conflicts.append(c)
    return all_conflicts


def _score(plan: Dict[int, list], classes: List[dict]) -> int:
    """软约束评分：返回惩罚分（越低越好）。硬约束已由放置时保证"""
    penalty = 0
    # S1 学生同日课间间隔 ≥ 30 分钟
    student_days = {}  # sid -> {weekday: [分钟列表]}
    for cls in classes:
        for item in plan.get(cls["id"], []):
            t0 = _to_min(item.get("start_time", ""))
            for sid in item.get("student_ids") or []:
                student_days.setdefault(sid, {}).setdefault(item["weekday"], []).append(t0)
    for sid, days in student_days.items():
        for day, times in days.items():
            times_sorted = sorted(times)
            for i in range(len(times_sorted) - 1):
                if times_sorted[i + 1] - times_sorted[i] < 30:
                    penalty += 2
    # S2 教师单日负荷 ≤ 3 节
    teacher_days = {}
    for cls in classes:
        tid = cls.get("teacher_id")
        if not tid:
            continue
        for item in plan.get(cls["id"], []):
            teacher_days.setdefault(tid, {}).setdefault(item["weekday"], 0)
            teacher_days[tid][item["weekday"]] += 1
    for tid, days in teacher_days.items():
        for day, cnt in days.items():
            if cnt > 3:
                penalty += cnt - 3
    return penalty


def _plan_key(plan: Dict[int, list]) -> str:
    """方案指纹（去重用）"""
    parts = []
    for cls_id in sorted(plan):
        for item in sorted(plan[cls_id], key=lambda x: (x["weekday"], x["start_time"])):
            parts.append(f"{cls_id}:{item['weekday']}-{item['start_time']}")
    return "|".join(parts)


def auto_plan(classes: List[dict], active_schedules: List[dict], period_slots: List[dict],
              num_solutions: int = 3, attempt_limit: int = 60) -> List[dict]:
    """智能排课，返回 Top-N 候选方案列表。

    classes: [{id, name, class_type, teacher_id, classroom_id, student_ids, weekly_frequency}]
    active_schedules: 已确认课次（status=active），参与冲突占用
    period_slots: [{weekday, start, end, label}]
    返回: [{score, unmet:[{class_id,name,need,got}], plan:{class_id:[课次...]}}]
    """
    occupied = [s for s in active_schedules if s.get("status") in ("active", None)]

    # 班级优先级：1v1 > 1vN；每周次数多 > 少；人数多 > 少
    def _priority(cls):
        return (0 if cls.get("class_type") == "1v1" else 1,
                -cls.get("weekly_frequency", 1),
                -(len(cls.get("student_ids") or [])))

    results = []
    seen = set()
    for attempt in range(attempt_limit):
        rng = random.Random(attempt)  # 确定性扰动：attempt 作种子
        shuffled = period_slots[:]
        rng.shuffle(shuffled)

        plan = {}
        unmet = []
        used = list(occupied)
        for cls in sorted(classes, key=_priority):
            placed = []
            need = cls.get("weekly_frequency", 1)
            for slot in shuffled:
                if len(placed) >= need:
                    break
                candidate = {
                    "class_id": cls["id"],
                    "weekday": slot["weekday"],
                    "start_time": slot["start"],
                    "end_time": slot["end"],
                    "classroom_id": cls.get("classroom_id"),
                    "teacher_id": cls.get("teacher_id"),
                    "student_ids": cls.get("student_ids") or [],
                }
                if not check_conflict(used, candidate):
                    placed.append(candidate)
                    used.append(candidate)
            if len(placed) < need:
                unmet.append({
                    "class_id": cls["id"],
                    "name": cls.get("name", ""),
                    "need": need,
                    "got": len(placed),
                })
            plan[cls["id"]] = placed

        key = _plan_key(plan)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "score": _score(plan, classes),
            "unmet": unmet,
            "plan": plan,
        })
        if len(results) >= num_solutions * 3:  # 防抖上限
            break

    results.sort(key=lambda r: (len(r["unmet"]), r["score"]))
    return results[:num_solutions]


def schedule_to_weekly(schedules: List[dict]) -> dict:
    """把课次列表转成周视图结构：{weekday: [课次...]}，供课表页渲染"""
    weekly = {d: [] for d in range(7)}
    for s in schedules:
        weekly.setdefault(s.get("weekday", 0), []).append(s)
    for d in weekly:
        weekly[d].sort(key=lambda x: x.get("start_time", ""))
    return weekly
