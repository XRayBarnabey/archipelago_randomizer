from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db import Base


def test_migration_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path}/m.db"
    cfg = Config("alembic.ini")
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    insp = inspect(create_engine(url))
    tables = set(insp.get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    for table in tables:
        assert {c["name"] for c in insp.get_columns(table)} == set(Base.metadata.tables[table].columns.keys())
    command.downgrade(cfg, "base")
