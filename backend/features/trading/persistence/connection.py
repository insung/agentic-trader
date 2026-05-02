"""Shared SQLite persistence path and connection helpers."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


PROJECT_ROOT = str(Path(__file__).resolve().parents[4])


def ensure_parent_dir(db_path: str) -> None:
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def connect(db_path: str) -> sqlite3.Connection:
    ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

