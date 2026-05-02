# -*- coding: utf-8 -*-
"""Tests del script de inicialización del GeoPackage (scripts/init_gpkg.py).

Valida los criterios de aceptación:
  - Se crean las tres tablas del MER (sessions, detections, annotations).
  - Las tablas espaciales están registradas en gpkg_contents y
    gpkg_geometry_columns con el SRS correcto.
  - Las relaciones de FK están declaradas correctamente.
  - El archivo es un GeoPackage 1.3 estándar (magic numbers OGC).
  - Se puede insertar la cadena session -> detection -> annotation
    respetando integridad referencial.

Estos tests no requieren QGIS ni GDAL: solo sqlite3 de stdlib.
"""

import os
import sqlite3
import sys

import pytest

# Agregar la raíz del repo al sys.path para poder importar scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.init_gpkg import (  # noqa: E402
    GPKG_APPLICATION_ID,
    GPKG_USER_VERSION,
    SUPPORTED_CRS,
    init_gpkg,
)


@pytest.fixture
def gpkg_path(tmp_path):
    """Crea un .gpkg fresco en un tmp dir y devuelve su ruta."""
    path = tmp_path / "test.gpkg"
    return init_gpkg(str(path), crs_epsg=32719)


# ---------------------------------------------------------------------------
# Estructura básica
# ---------------------------------------------------------------------------

def test_gpkg_magic_numbers(gpkg_path):
    """application_id y user_version deben coincidir con OGC 1.3."""
    conn = sqlite3.connect(gpkg_path)
    try:
        app_id = conn.execute("PRAGMA application_id;").fetchone()[0]
        user_version = conn.execute("PRAGMA user_version;").fetchone()[0]
    finally:
        conn.close()
    assert app_id == GPKG_APPLICATION_ID
    assert user_version == GPKG_USER_VERSION


def test_three_mer_tables_exist(gpkg_path):
    """Las tablas sessions, detections y annotations deben existir."""
    conn = sqlite3.connect(gpkg_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name IN ('sessions','detections','annotations');"
        ).fetchall()
    finally:
        conn.close()
    names = {r[0] for r in rows}
    assert names == {"sessions", "detections", "annotations"}


def test_sessions_has_no_geometry(gpkg_path):
    """sessions es tabla atributiva, no debe tener columna geom."""
    conn = sqlite3.connect(gpkg_path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions);")]
    finally:
        conn.close()
    assert "geom" not in cols
    # Campos del MER que sí esperamos.
    assert "started_at" in cols
    assert "image_path" in cols


def test_spatial_tables_have_polygon_geometry(gpkg_path):
    """detections y annotations deben tener columna geom registrada."""
    conn = sqlite3.connect(gpkg_path)
    try:
        rows = conn.execute(
            "SELECT table_name, column_name, geometry_type_name, srs_id "
            "FROM gpkg_geometry_columns ORDER BY table_name;"
        ).fetchall()
    finally:
        conn.close()
    assert ("annotations", "geom", "POLYGON", 32719) in rows
    assert ("detections", "geom", "POLYGON", 32719) in rows


# ---------------------------------------------------------------------------
# Compatibilidad con QGIS nativo
# ---------------------------------------------------------------------------

def test_gpkg_contents_registers_all_three_tables(gpkg_path):
    """gpkg_contents debe registrar las 3 tablas con el data_type correcto.

    QGIS solo muestra como capa lo que esté aquí declarado.
    """
    conn = sqlite3.connect(gpkg_path)
    try:
        rows = conn.execute(
            "SELECT table_name, data_type FROM gpkg_contents "
            "ORDER BY table_name;"
        ).fetchall()
    finally:
        conn.close()
    contents = dict(rows)
    assert contents["sessions"] == "attributes"
    assert contents["detections"] == "features"
    assert contents["annotations"] == "features"


def test_srs_seed_present(gpkg_path):
    """gpkg_spatial_ref_sys debe contener -1, 0, 4326 y el SRS pedido."""
    conn = sqlite3.connect(gpkg_path)
    try:
        ids = {
            r[0]
            for r in conn.execute("SELECT srs_id FROM gpkg_spatial_ref_sys;")
        }
    finally:
        conn.close()
    assert {-1, 0, 4326, 32719}.issubset(ids)


def test_rtree_index_exists(gpkg_path):
    """Debe existir el R-tree espacial para ambas tablas con geometría."""
    conn = sqlite3.connect(gpkg_path)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'rtree_%';"
            )
        }
    finally:
        conn.close()
    # El R-tree virtual genera tabla principal + _node + _parent + _rowid.
    assert "rtree_annotations_geom" in names
    assert "rtree_detections_geom" in names


# ---------------------------------------------------------------------------
# Integridad referencial (FK)
# ---------------------------------------------------------------------------

def test_foreign_keys_declared(gpkg_path):
    """annotations debe declarar FK a sessions y a detections."""
    conn = sqlite3.connect(gpkg_path)
    try:
        ann_fks = conn.execute(
            "PRAGMA foreign_key_list(annotations);"
        ).fetchall()
        det_fks = conn.execute(
            "PRAGMA foreign_key_list(detections);"
        ).fetchall()
    finally:
        conn.close()

    # Cada fila: (id, seq, table, from, to, on_update, on_delete, match).
    ann_targets = {(r[2], r[3]) for r in ann_fks}
    det_targets = {(r[2], r[3]) for r in det_fks}
    assert ("sessions", "session_id") in ann_targets
    assert ("detections", "detection_id") in ann_targets
    assert ("sessions", "session_id") in det_targets


def test_insert_chain_session_detection_annotation(gpkg_path):
    """Insertar una cadena completa session -> detection -> annotation."""
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO sessions (started_at, image_path, model_version, user) "
            "VALUES (?, ?, ?, ?);",
            ("2026-04-25T10:00:00Z", "/data/cerro_unita.tif", "sam_vit_h", "fer"),
        )
        sid = cur.lastrowid

        # Geometría dummy (un BLOB cualquiera; aquí no validamos la spec WKB).
        dummy_geom = b"\x00" * 32
        cur.execute(
            "INSERT INTO detections "
            "(geom, session_id, confidence, priority, model_version, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (dummy_geom, sid, 0.87, 1, "sam_vit_h", "2026-04-25T10:05:00Z"),
        )
        det_id = cur.lastrowid

        cur.execute(
            "INSERT INTO annotations "
            "(geom, session_id, detection_id, label, origin, status, "
            " confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (dummy_geom, sid, det_id, "antropomorfo",
             "ml", "approved", 0.87, "2026-04-25T10:06:00Z"),
        )
        ann_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    assert sid > 0 and det_id > 0 and ann_id > 0


def test_fk_violation_rejected(gpkg_path):
    """Insertar annotation con session_id inexistente debe fallar."""
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO annotations "
                "(geom, session_id, origin, created_at) "
                "VALUES (?, ?, ?, ?);",
                (b"\x00" * 32, 99999, "human", "2026-04-25T10:00:00Z"),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Validaciones de dominio (CHECK constraints)
# ---------------------------------------------------------------------------

def test_origin_check_constraint(gpkg_path):
    """origin solo debe aceptar 'ml' o 'human'."""
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            "INSERT INTO sessions (started_at, image_path) VALUES (?, ?);",
            ("2026-04-25T10:00:00Z", "/x.tif"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO annotations "
                "(geom, session_id, origin, created_at) "
                "VALUES (?, ?, ?, ?);",
                (b"\x00" * 32, 1, "robot", "2026-04-25T10:00:00Z"),
            )
    finally:
        conn.close()


def test_status_check_constraint(gpkg_path):
    """status solo debe aceptar pending/approved/rejected."""
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            "INSERT INTO sessions (started_at, image_path) VALUES (?, ?);",
            ("2026-04-25T10:00:00Z", "/x.tif"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO annotations "
                "(geom, session_id, origin, status, created_at) "
                "VALUES (?, ?, ?, ?, ?);",
                (b"\x00" * 32, 1, "human", "maybe", "2026-04-25T10:00:00Z"),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI / errores de uso
# ---------------------------------------------------------------------------

def test_invalid_crs_raises(tmp_path):
    """Un CRS no soportado debe lanzar ValueError."""
    with pytest.raises(ValueError):
        init_gpkg(str(tmp_path / "x.gpkg"), crs_epsg=12345)


def test_existing_file_without_overwrite_raises(tmp_path):
    """Si el archivo existe y overwrite=False, debe fallar."""
    path = str(tmp_path / "x.gpkg")
    init_gpkg(path)
    with pytest.raises(FileExistsError):
        init_gpkg(path)


def test_existing_file_with_overwrite_succeeds(tmp_path):
    """Con overwrite=True el archivo se reemplaza correctamente."""
    path = str(tmp_path / "x.gpkg")
    init_gpkg(path)
    out = init_gpkg(path, overwrite=True)
    assert os.path.exists(out)


def test_supported_crs_list_includes_atacama_default():
    """El default 32719 debe estar en SUPPORTED_CRS."""
    assert 32719 in SUPPORTED_CRS
