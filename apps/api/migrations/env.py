from alembic import context

from talent_api import models  # noqa: F401 — register ORM metadata
from talent_api.db import Base, engine

target_metadata = Base.metadata


def run_online(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    from talent_api.config import settings

    context.configure(
        url=settings.database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    # Tests pass an isolated transactional connection; normal CLI uses the app engine.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        run_online(connection)
    else:
        with engine.connect() as connection:
            run_online(connection)
