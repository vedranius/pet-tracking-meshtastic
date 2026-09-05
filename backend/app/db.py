import os

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine

DATA_DIR = os.environ.get("PAWTRACK_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "pawtrack.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

# create_all() only creates tables that don't exist yet — it never alters an
# existing table's columns. Since this project has no migration framework,
# new nullable columns added to an existing table are applied by hand here
# so an upgrade (git pull + restart) never breaks on "no such column" for
# anyone who already has a database from before that column existed.
_COLUMN_MIGRATIONS: dict[str, list[str]] = {
    "user": [
        "ALTER TABLE user ADD COLUMN bio VARCHAR",
        "ALTER TABLE user ADD COLUMN avatar_path VARCHAR",
        "ALTER TABLE user ADD COLUMN avatar_mime VARCHAR",
        "ALTER TABLE user ADD COLUMN location_sharing_enabled BOOLEAN DEFAULT 1 NOT NULL",
    ],
}


def _run_column_migrations() -> None:
    with engine.begin() as conn:
        for table, statements in _COLUMN_MIGRATIONS.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if not existing:
                continue  # table doesn't exist yet — create_all() will make it with all columns already
            for stmt in statements:
                column = stmt.split("ADD COLUMN")[1].split()[0]
                if column not in existing:
                    conn.execute(text(stmt))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _run_column_migrations()


def get_session() -> Session:
    return Session(engine)
