"""SQLite connection and migration helpers."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from time import time

from storage.migrations import MIGRATIONS


class Database:
    """Light async wrapper around sqlite3 with serialized access."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        self._connection = connection

    async def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not connected")
        return self._connection

    async def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
        async with self._lock:
            cursor = self.connection.execute(sql, parameters)
            self.connection.commit()
            return cursor

    async def executemany(self, sql: str, seq_of_parameters: list[tuple[object, ...]]) -> sqlite3.Cursor:
        async with self._lock:
            cursor = self.connection.executemany(sql, seq_of_parameters)
            self.connection.commit()
            return cursor

    async def fetchone(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Row | None:
        async with self._lock:
            cursor = self.connection.execute(sql, parameters)
            return cursor.fetchone()

    async def fetchall(self, sql: str, parameters: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        async with self._lock:
            cursor = self.connection.execute(sql, parameters)
            return list(cursor.fetchall())

    async def apply_migrations(self) -> None:
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                applied_at INTEGER NOT NULL
            )
            """
        )
        applied = {
            row["name"]
            for row in await self.fetchall("SELECT name FROM schema_migrations")
        }
        for name, sql in MIGRATIONS:
            if name in applied:
                continue
            async with self._lock:
                self.connection.executescript(sql)
                self.connection.execute(
                    "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                    (name, int(time())),
                )
                self.connection.commit()
