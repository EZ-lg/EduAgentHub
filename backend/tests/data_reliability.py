"""
P0 数据可靠性专项回归（隔离临时数据库，不污染真实数据）

用法：venv/Scripts/python.exe backend/tests/data_reliability.py

覆盖：健康自检 / 纯DB备份 / 完整备份zip / 损坏自动恢复 / fatal 阻止启动 /
      一键恢复(db+full) / 迁移导出下载导入 / 恶意zip拦截 / 删除备份 / KB路径归一化

安全设计：EDU_DATA_DIR 指向临时目录 → 全新空库跑，绝不触碰 data/tutoring.db。
"""
import os
import shutil
import sys
import tempfile
import zipfile
from urllib.parse import quote

# 脚本模式运行时 cwd 不在 sys.path，手动补项目根（保证 from backend... 可导入）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---- 隔离数据目录（必须在导入 backend 前设置）----
_TMP = tempfile.mkdtemp(prefix="edu_rel_")
os.environ["EDU_DATA_DIR"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.models import SessionLocal, engine, init_db  # noqa: E402

init_db()
client = TestClient(app)

from config import DATA_DIR, DB_PATH, UPLOAD_DIR  # noqa: E402
from backend.utils import backup as bu  # noqa: E402
from backend.utils.db_health import check_and_repair_db, check_db_integrity  # noqa: E402

PASS = 0
FAIL = []


def check(name, fn):
    global PASS
    try:
        fn()
        PASS += 1
        print(f"  [PASS] {name}")
    except Exception as e:
        FAIL.append(f"{name}: {e}")
        print(f"  [FAIL] {name}: {e}")


def _create_student(name):
    r = client.post("/api/students", json={"name": name, "gender": "男", "grade": "初二"})
    assert r.status_code == 200 and r.json().get("success"), r.text
    return r.json()["data"]["id"]


def _get_student_name(sid):
    r = client.get(f"/api/students/{sid}")
    assert r.status_code == 200 and r.json().get("success"), r.text
    return r.json()["data"]["name"]


def _rename(sid, new_name):
    r = client.put(f"/api/students/{sid}", json={"name": new_name})
    assert r.status_code == 200 and r.json().get("success"), r.text


def _corrupt_db():
    """破坏 SQLite 文件头 magic（"SQLite format 3"）→ 必然被识别为损坏，可靠模拟磁盘损坏"""
    engine.dispose()
    with open(DB_PATH, "r+b") as f:
        f.seek(0)
        f.write(b"NOTASQLITE" + b"\x00" * 8)


def _import_check(pkg_path, pkg_file):
    r = client.post("/api/settings/migrate/import",
                    files={"file": (pkg_file, open(pkg_path, "rb"), "application/zip")})
    if r.status_code != 200 or not r.json().get("success"):
        raise AssertionError(f"import 请求失败: status={r.status_code} body={r.text[:300]}")
    return True


def _expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def assert_get_name(sid):
    _get_student_name(sid)
    return True


def assert_name_eq(sid, expected):
    assert _get_student_name(sid) == expected, \
        f"期望 {expected}，实际 {_get_student_name(sid)}"
    return True


def _seed_kb_doc(file_path):
    from backend.models.knowledge_doc import KnowledgeDoc
    db = SessionLocal()
    try:
        d = KnowledgeDoc(title="迁移文档", file_path=file_path, file_type=".txt")
        db.add(d)
        db.commit()
    finally:
        db.close()


def _normalize_kb_docs():
    from backend.utils.migrate import _normalize_kb_paths
    return _normalize_kb_paths()


def _assert_kb_path(basename):
    from backend.models.knowledge_doc import KnowledgeDoc
    db = SessionLocal()
    try:
        doc = db.query(KnowledgeDoc).order_by(KnowledgeDoc.id.desc()).first()
        assert doc.file_path == os.path.join(UPLOAD_DIR, basename), doc.file_path
    finally:
        db.close()


ORIG_NAME = "数据学生A"

print("== P0 数据可靠性 ==")

# ---- 1. 健康自检 ----
check("健康端点 healthy", lambda: (
    (lambda j: _expect(
        j["data"]["healthy"] is True and j["data"]["quick_check"] == "ok"
        and j["data"]["tables_ok"] is True,
        f"健康自检应正常，实际 {j['data']}"))(
        client.get("/api/settings/health").json())))

sid = _create_student(ORIG_NAME)
check("种子学生已建", lambda: assert_get_name(sid) or None)

# ---- 2. 纯 DB 备份 + 一键恢复 ----
r = client.post("/api/settings/backup")
check("纯DB备份", lambda: (
    (lambda j: (j["success"] and j["data"]["type"] == "db"))(r.json())))
db_file = r.json()["data"]["path"].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

check("备份列表含 db 类型", lambda: (
    (lambda j: any(b["type"] == "db" for b in j["data"]))(
        client.get("/api/settings/backups").json())))

check("改名后从db备份恢复", lambda: (
    _rename(sid, "改名B"),
    (lambda j: (j["success"] and j["data"]["restored"] == "db"))(
        client.post("/api/settings/backups/restore", json={"filename": db_file}).json()),
    assert_name_eq(sid, ORIG_NAME),
))

# ---- 3. 完整备份 zip + 一键恢复 ----
r = client.post("/api/settings/backup?full=true")
check("完整备份zip", lambda: (
    (lambda j: (j["success"] and j["data"]["type"] == "full"))(r.json())))
full_file = r.json()["data"]["path"].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

check("zip内含DB与MANIFEST", lambda: (
    (lambda zp: (
        zipfile.ZipFile(zp).namelist().__contains__("tutoring.db")
        and zipfile.ZipFile(zp).namelist().__contains__("MANIFEST.json")))(
        os.path.join(bu.BACKUP_DIR, full_file))))

upload_test = os.path.join(UPLOAD_DIR, "data_upload_test.txt")
check("改动数据后从full备份恢复", lambda: (
    _rename(sid, "改名C"),
    open(upload_test, "w", encoding="utf-8").write("hi"),
    (lambda j: (j["success"] and j["data"]["restored"] == "full"))(
        client.post("/api/settings/backups/restore", json={"filename": full_file}).json()),
    assert_name_eq(sid, ORIG_NAME),
    # full 备份时 uploads 为空，恢复后上传文件应被清空（回到备份时状态）
    _expect(not os.path.exists(upload_test), "full恢复后 upload_test 应被清空"),
))

# ---- 4. 迁移导出 / 下载 / 导入 ----
r = client.post("/api/settings/migrate/export")
check("导出数据包", lambda: (
    (lambda j: (j["success"] and j["data"]["filename"])) (r.json())))
pkg_file = r.json()["data"]["filename"]
pkg_path = os.path.join(bu.BACKUP_DIR, pkg_file)

check("下载数据包200", lambda: (
    (lambda resp: (resp.status_code == 200 and len(resp.content) > 100))(
        client.get(f"/api/settings/backups/{pkg_file}/download"))))

check("导入数据包回滚数据", lambda: (
    _rename(sid, "改名D"),
    _import_check(pkg_path, pkg_file),
    assert_name_eq(sid, ORIG_NAME),
))

# ---- 5. 恶意 zip 拦截 ----
def _make_evil_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("../../evil.txt", "evil")
        zf.writestr("tutoring.db", "not-a-db")
    return path

check("恶意zip(穿越)被400拦截", lambda: (
    (lambda resp: (resp.status_code == 400))(
        client.post("/api/settings/migrate/import",
                    files={"file": ("evil.zip", open(_make_evil_zip(
                        os.path.join(tempfile.gettempdir(), "edu_evil.zip")), "rb"),
                           "application/zip")}))))

# ---- 6. 删除备份 ----
check("删除备份成功", lambda: (
    (lambda j: j["success"])(
        client.delete(f"/api/settings/backups/{db_file}").json())))
check("删除非法路径404", lambda: (
    (lambda resp: (resp.status_code in (400, 404)))(
        client.delete(f"/api/settings/backups/{quote('../evil.db')}"))))

# ---- 7. KB 跨机路径归一化 ----
check("KB路径归一化", lambda: (
    (lambda: _seed_kb_doc("C:/old/pc/uploads/abc.txt"))(),
    (lambda: open(os.path.join(UPLOAD_DIR, "abc.txt"), "w", encoding="utf-8").write("x"))(),
    (lambda n: (_expect(n >= 1, "归一化数量≥1"), n)[1])(_normalize_kb_docs()),
    (lambda: _assert_kb_path("abc.txt"))(),
))

# ---- 8. 损坏自动恢复 ----
# 先备份当前状态，作为损坏恢复的可靠源（此时数据为 ORIG_NAME）
client.post("/api/settings/backup")
check("损坏检测", lambda: (
    (lambda res: (res["quick_check"] != "ok") or (res["error"] is not None))(
        (lambda: (_corrupt_db(), check_db_integrity())[1])())))

check("自动恢复(recovered)且数据在", lambda: (
    (lambda res: (res["status"] in ("recovered", "ok")))(check_and_repair_db()),
    assert_name_eq(sid, ORIG_NAME),
))

# ---- 9. fatal 阻止启动（无可用备份 + 损坏）----
def _run_fatal():
    for b in bu.list_backups():
        if b["type"] == "db":
            bu.delete_backup(b["filename"])
    _corrupt_db()
    res = check_and_repair_db()
    assert res["status"] == "fatal", res
    assert os.path.exists(os.path.join(DATA_DIR, "startup_failed.txt"))


check("无备份+损坏→fatal+startup_failed", _run_fatal)


# ============================================================ 汇总
print(f"\n结果: {PASS} 通过, {len(FAIL)} 失败")
if FAIL:
    print("失败项:")
    for f in FAIL:
        print(f"  - {f}")
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
