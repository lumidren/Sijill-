from __future__ import annotations

from alembic import context

from app import models  # noqa: F401  (register tables)
from app.db import Base, get_engine, make_engine

target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = context.config.attributes.get("url")
    engine = make_engine(url) if url else get_engine()
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata,
                          render_as_batch=conn.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
