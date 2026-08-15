"""
数据库方言层 — SQLite / PostgreSQL / MySQL 等差异收敛于此（2.0 可迁移化）

原则：ORM 层不出现方言细节。未来切 PostgreSQL/MySQL 只需：
  1. 设置环境变量 EDU_DATABASE_URL 指向新库
  2. 如有必要在本文件补充该方言的特殊 connect_args / 事件

SQLite 特有处理（其余方言自动跳过）：
  - connect_args check_same_thread=False（SQLite 线程安全检查）
  - PRAGMA foreign_keys=ON（级联删除命根子，见 backend/models/__init__.py 注释）
"""
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine


def get_db_type(database_url: str) -> str:
    """返回方言类型：'sqlite' / 'postgresql' / 'mysql' 等（去驱动前缀）"""
    return database_url.split(":", 1)[0].split("+", 1)[0].lower()


def create_app_engine(database_url: str, echo: bool = False) -> Engine:
    """按方言创建 engine

    - SQLite：check_same_thread=False + 每个连接开启外键
    - 其他方言：默认 connect_args（后续按需在 get_connect_args 中补充）
    """
    connect_args = {}
    if get_db_type(database_url) == "sqlite":
        connect_args = {"check_same_thread": False}

    engine = create_engine(database_url, connect_args=connect_args, echo=echo)

    # SQLite 默认不启用外键约束，导致 ON DELETE CASCADE 不生效
    # （删除学生后学科残留，且 ID 复用会让新学生"继承"旧学科 —— P3 已踩坑）
    if get_db_type(database_url) == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
            except Exception:
                pass  # 非 SQLite 或其他驱动忽略

    return engine


def run_light_migrations(engine: Engine, rules: dict) -> None:
    """轻量列迁移：create_all 不会为已有表加新列，这里补齐。

    rules: {table_name: {"cols": {column_name: ddl_type_str}}}
    示例：
      rules = {"knowledge_docs": {"cols": {"index_status": "VARCHAR DEFAULT 'done'"}}}

    ALTER TABLE ... ADD COLUMN 为标准 SQL（PostgreSQL/MySQL 均支持），
    仅类型写法可能有方言差异，届时在此按 get_db_type 分支即可。
    """
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for table, cfg in rules.items():
        if table not in tables:
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        adds = []
        for col, col_type in cfg["cols"].items():
            if col not in cols:
                adds.append(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        if adds:
            with engine.begin() as conn:
                for stmt in adds:
                    conn.execute(text(stmt))
