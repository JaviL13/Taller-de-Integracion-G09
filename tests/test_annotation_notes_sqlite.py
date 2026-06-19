# -*- coding: utf-8 -*-
"""Tests puros (sqlite3, sin QGIS) del esquema annotation_notes — TIGS-87.

Valida que init_gpkg crea correctamente la tabla annotation_notes con
los campos, índice y comportamiento append-only requeridos por el
criterio de trazabilidad de CENIA.

No requieren QGIS ni GDAL: solo sqlite3 de stdlib + scripts/init_gpkg.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.init_gpkg import init_gpkg  # noqa: E402


@pytest.fixture
def gpkg_path(tmp_path):
    return init_gpkg(str(tmp_path / "test.gpkg"), crs_epsg=32719)


# ── Estructura de la tabla ────────────────────────────────────────────────────


def test_tabla_annotation_notes_existe(gpkg_path):
    """init_gpkg debe crear la tabla annotation_notes junto con las demás."""
    conn = sqlite3.connect(gpkg_path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    finally:
        conn.close()
    assert "annotation_notes" in tables


def test_annotation_notes_campos_correctos(gpkg_path):
    """annotation_notes debe tener los campos del MER de trazabilidad."""
    conn = sqlite3.connect(gpkg_path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(annotation_notes);").fetchall()]
    finally:
        conn.close()
    for campo in ("id", "annotation_id", "texto", "origen", "estado", "score", "timestamp"):
        assert campo in cols, f"Campo '{campo}' no encontrado en annotation_notes"


def test_annotation_notes_indice_existe(gpkg_path):
    """Debe existir un índice sobre annotation_id para acelerar las queries."""
    conn = sqlite3.connect(gpkg_path)
    try:
        indices = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index';").fetchall()}
    finally:
        conn.close()
    assert "idx_annotation_notes_annotation_id" in indices


# ── Comportamiento append-only ────────────────────────────────────────────────


def test_annotation_notes_append_only(gpkg_path):
    """Insertar dos notas para la misma annotation_id conserva ambas."""
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        # Semilla mínima para satisfacer FKs.
        conn.execute(
            "INSERT INTO sessions (started_at, image_path) VALUES (?, ?);",
            ("2026-05-25T10:00:00Z", "/img.tif"),
        )
        dummy_geom = b"\x00" * 32
        conn.execute(
            "INSERT INTO annotations (geom, session_id, origin, created_at) VALUES (?, ?, ?, ?);",
            (dummy_geom, 1, "human", "2026-05-25T10:01:00Z"),
        )
        ann_id = conn.execute("SELECT last_insert_rowid();").fetchone()[0]

        conn.execute(
            "INSERT INTO annotation_notes (annotation_id, texto, origen, estado, timestamp) VALUES (?, ?, ?, ?, ?);",
            (ann_id, "nota uno", "human-annotation", "pending", "2026-05-25T10:02:00Z"),
        )
        conn.execute(
            "INSERT INTO annotation_notes (annotation_id, texto, origen, estado, timestamp) VALUES (?, ?, ?, ?, ?);",
            (ann_id, "nota dos", "human-annotation", "approved", "2026-05-25T10:03:00Z"),
        )
        conn.commit()

        rows = conn.execute(
            "SELECT texto, estado FROM annotation_notes WHERE annotation_id = ? ORDER BY timestamp;",
            (ann_id,),
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    assert rows[0] == ("nota uno", "pending")
    assert rows[1] == ("nota dos", "approved")


def test_annotation_notes_estado_check_constraint(gpkg_path):
    """El campo estado solo debe aceptar 'pending', 'approved' o 'rejected'."""
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            "INSERT INTO sessions (started_at, image_path) VALUES (?, ?);",
            ("2026-05-25T10:00:00Z", "/img.tif"),
        )
        dummy_geom = b"\x00" * 32
        conn.execute(
            "INSERT INTO annotations (geom, session_id, origin, created_at) VALUES (?, ?, ?, ?);",
            (dummy_geom, 1, "human", "2026-05-25T10:01:00Z"),
        )
        ann_id = conn.execute("SELECT last_insert_rowid();").fetchone()[0]

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO annotation_notes (annotation_id, texto, origen, estado, timestamp) "
                "VALUES (?, ?, ?, ?, ?);",
                (ann_id, "nota", "human-annotation", "estado_invalido", "2026-05-25T10:02:00Z"),
            )
    finally:
        conn.close()
