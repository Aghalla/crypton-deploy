"""Enable WAL mode for SQLite via the connection_created signal."""
from django.db.backends.signals import connection_created


def enable_sqlite_wal(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA synchronous=NORMAL;')


connection_created.connect(enable_sqlite_wal)
