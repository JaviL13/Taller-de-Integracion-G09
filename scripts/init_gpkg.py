# -*- coding: utf-8 -*-
"""Inicialización del GeoPackage de GeoGlyph (TIGS - persistencia MER).

Crea un archivo .gpkg vacío con las tres tablas del Modelo Entidad-Relación
descritas en la sección 5 del Documento de Diseño:

    sessions      - sesiones de trabajo del usuario (sin geometría)
    detections    - candidatos importados desde modelos externos (POLYGON)
    annotations   - anotaciones validadas por el arqueólogo (POLYGON)

Las relaciones de Foreign Key entre las tres tablas permiten reconstruir
el origen y el historial de validación de cada anotación
(requisito de trazabilidad - sección 7.4 de la spec CENIA).

El archivo resultante es un GeoPackage 1.3 estándar OGC, compatible con
QGIS nativo: las dos tablas espaciales aparecen como capas vectoriales
y la tabla `sessions` aparece como tabla atributiva.

Uso desde CLI:
    python scripts/init_gpkg.py annotations.gpkg --crs 32719

Uso desde Python:
    from scripts.init_gpkg import init_gpkg
    init_gpkg('annotations.gpkg', crs_epsg=32719)

Solo depende de la stdlib (sqlite3) - no requiere QGIS, GDAL ni PyQt.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Constantes del estándar OGC GeoPackage 1.3
# ---------------------------------------------------------------------------

# Magic number "GPKG" en ASCII como entero big-endian, requerido por la
# spec OGC para que el archivo se reconozca como GeoPackage (no solo SQLite).
GPKG_APPLICATION_ID = 0x47504B47  # 1196444487

# user_version = 10300 corresponde a GeoPackage 1.3.0 (formato MMmmpp).
GPKG_USER_VERSION = 10300

# WKT de los CRS soportados. Mantener el WKT inline evita depender de PROJ.
# Si el equipo necesita más CRS, agregar aquí su par (epsg, wkt).
SUPPORTED_CRS = {
    4326: (
        'GEOGCS["WGS 84",'
        'DATUM["WGS_1984",'
        'SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
        'AUTHORITY["EPSG","6326"]],'
        'PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
        'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
        'AUTHORITY["EPSG","4326"]]'
    ),
    32719: (
        'PROJCS["WGS 84 / UTM zone 19S",'
        'GEOGCS["WGS 84",'
        'DATUM["WGS_1984",'
        'SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
        'AUTHORITY["EPSG","6326"]],'
        'PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
        'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
        'AUTHORITY["EPSG","4326"]],'
        'PROJECTION["Transverse_Mercator"],'
        'PARAMETER["latitude_of_origin",0],'
        'PARAMETER["central_meridian",-69],'
        'PARAMETER["scale_factor",0.9996],'
        'PARAMETER["false_easting",500000],'
        'PARAMETER["false_northing",10000000],'
        'UNIT["metre",1,AUTHORITY["EPSG","9001"]],'
        'AXIS["Easting",EAST],AXIS["Northing",NORTH],'
        'AUTHORITY["EPSG","32719"]]'
    ),
}


# ---------------------------------------------------------------------------
# DDL de las tablas obligatorias del estándar OGC
# ---------------------------------------------------------------------------

DDL_GPKG_SPATIAL_REF_SYS = """
CREATE TABLE gpkg_spatial_ref_sys (
    srs_name                 TEXT      NOT NULL,
    srs_id                   INTEGER   NOT NULL PRIMARY KEY,
    organization             TEXT      NOT NULL,
    organization_coordsys_id INTEGER   NOT NULL,
    definition               TEXT      NOT NULL,
    description              TEXT
);
"""

DDL_GPKG_CONTENTS = """
CREATE TABLE gpkg_contents (
    table_name  TEXT     NOT NULL PRIMARY KEY,
    data_type   TEXT     NOT NULL,
    identifier  TEXT     UNIQUE,
    description TEXT     DEFAULT '',
    last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    min_x       DOUBLE,
    min_y       DOUBLE,
    max_x       DOUBLE,
    max_y       DOUBLE,
    srs_id      INTEGER,
    CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id)
        REFERENCES gpkg_spatial_ref_sys(srs_id)
);
"""

DDL_GPKG_GEOMETRY_COLUMNS = """
CREATE TABLE gpkg_geometry_columns (
    table_name         TEXT    NOT NULL,
    column_name        TEXT    NOT NULL,
    geometry_type_name TEXT    NOT NULL,
    srs_id             INTEGER NOT NULL,
    z                  TINYINT NOT NULL,
    m                  TINYINT NOT NULL,
    CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
    CONSTRAINT uk_gc_table_name UNIQUE (table_name),
    CONSTRAINT fk_gc_tn FOREIGN KEY (table_name)
        REFERENCES gpkg_contents(table_name),
    CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id)
        REFERENCES gpkg_spatial_ref_sys(srs_id)
);
"""

DDL_GPKG_EXTENSIONS = """
CREATE TABLE gpkg_extensions (
    table_name     TEXT,
    column_name    TEXT,
    extension_name TEXT NOT NULL,
    definition     TEXT NOT NULL,
    scope          TEXT NOT NULL,
    CONSTRAINT ge_tce UNIQUE (table_name, column_name, extension_name)
);
"""

# Tabla auxiliar que OGR escribe automáticamente. La incluimos para que el
# archivo sea bit-a-bit compatible con los .gpkg que crea QGIS / OGR.
DDL_GPKG_OGR_CONTENTS = """
CREATE TABLE gpkg_ogr_contents (
    table_name TEXT NOT NULL PRIMARY KEY,
    feature_count INTEGER DEFAULT NULL
);
"""


# ---------------------------------------------------------------------------
# DDL de las tres tablas del MER
# ---------------------------------------------------------------------------

DDL_SESSIONS = """
CREATE TABLE sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT    NOT NULL,
    ended_at      TEXT,
    image_path    TEXT    NOT NULL,
    model_version TEXT,
    user          TEXT
);
"""

DDL_DETECTIONS = """
CREATE TABLE detections (
    fid           INTEGER PRIMARY KEY AUTOINCREMENT,
    geom          BLOB    NOT NULL,
    session_id    INTEGER NOT NULL,
    confidence    REAL    NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 0,
    model_version TEXT,
    imported_at   TEXT    NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
"""

DDL_ANNOTATIONS = """
CREATE TABLE annotations (
    fid           INTEGER PRIMARY KEY AUTOINCREMENT,
    geom          BLOB    NOT NULL,
    session_id    INTEGER NOT NULL,
    detection_id  INTEGER,
    label         TEXT,
    origin        TEXT    NOT NULL CHECK(origin IN ('ml','human')),
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','approved','rejected')),
    confidence    REAL,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (session_id)   REFERENCES sessions(id),
    FOREIGN KEY (detection_id) REFERENCES detections(fid)
);
"""

# Índices en las FK para acelerar las queries de trazabilidad.
DDL_INDEXES = [
    "CREATE INDEX idx_detections_session_id ON detections(session_id);",
    "CREATE INDEX idx_annotations_session_id ON annotations(session_id);",
    "CREATE INDEX idx_annotations_detection_id ON annotations(detection_id);",
    "CREATE INDEX idx_annotations_status ON annotations(status);",
]


# ---------------------------------------------------------------------------
# DDL del índice R-tree (formato OGC GeoPackage)
# ---------------------------------------------------------------------------

def _rtree_ddl(table: str) -> list[str]:
    """Devuelve las sentencias para crear el R-tree espacial de una tabla.

    El R-tree de GeoPackage se materializa como una tabla virtual + 3 tablas
    auxiliares (`_node`, `_parent`, `_rowid`). QGIS crea esto automáticamente
    cuando guarda capas, y lo replicamos aquí para tener el mismo formato.
    """
    return [
        f"""CREATE VIRTUAL TABLE rtree_{table}_geom USING rtree(
            id, minx, maxx, miny, maxy
        );""",
    ]


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def init_gpkg(path: str, crs_epsg: int = 32719, overwrite: bool = False) -> str:
    """Crea un GeoPackage vacío con el esquema MER de GeoGlyph.

    Args:
        path: Ruta donde se creará el archivo .gpkg.
        crs_epsg: Código EPSG del CRS para las tablas espaciales.
            Por defecto 32719 (UTM 19S - Atacama, Chile).
        overwrite: Si True, sobrescribe el archivo si ya existe.

    Returns:
        La ruta absoluta del archivo creado.

    Raises:
        FileExistsError: si `path` existe y `overwrite=False`.
        ValueError: si `crs_epsg` no está en SUPPORTED_CRS.
    """
    if crs_epsg not in SUPPORTED_CRS:
        raise ValueError(
            f"CRS EPSG:{crs_epsg} no soportado. "
            f"Disponibles: {sorted(SUPPORTED_CRS)}"
        )

    path = os.path.abspath(path)
    if os.path.exists(path):
        if not overwrite:
            raise FileExistsError(
                f"{path} ya existe. Usa overwrite=True para reemplazar."
            )
        os.remove(path)

    # Aseguramos que el directorio destino exista (ej: scripts/, data/).
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()

        # -- 1. Magic numbers OGC: convierten un .sqlite común en un .gpkg.
        cur.execute(f"PRAGMA application_id = {GPKG_APPLICATION_ID};")
        cur.execute(f"PRAGMA user_version = {GPKG_USER_VERSION};")

        # -- 2. Habilitar FK enforcement (off por defecto en SQLite).
        cur.execute("PRAGMA foreign_keys = ON;")

        # -- 3. Tablas obligatorias del estándar OGC.
        cur.executescript(DDL_GPKG_SPATIAL_REF_SYS)
        cur.executescript(DDL_GPKG_CONTENTS)
        cur.executescript(DDL_GPKG_GEOMETRY_COLUMNS)
        cur.executescript(DDL_GPKG_EXTENSIONS)
        cur.executescript(DDL_GPKG_OGR_CONTENTS)

        # -- 4. Sembrar gpkg_spatial_ref_sys con los SRS exigidos por la spec
        #       (-1, 0) y los que usaremos (4326, 32719).
        srs_seed = [
            ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
            ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
            ("WGS 84", 4326, "EPSG", 4326, SUPPORTED_CRS[4326], None),
        ]
        if crs_epsg not in (4326, -1, 0):
            srs_seed.append(
                (
                    f"EPSG:{crs_epsg}",
                    crs_epsg,
                    "EPSG",
                    crs_epsg,
                    SUPPORTED_CRS[crs_epsg],
                    None,
                )
            )
        cur.executemany(
            "INSERT INTO gpkg_spatial_ref_sys "
            "(srs_name, srs_id, organization, organization_coordsys_id, "
            " definition, description) VALUES (?, ?, ?, ?, ?, ?);",
            srs_seed,
        )

        # -- 5. Tablas del MER.
        cur.executescript(DDL_SESSIONS)
        cur.executescript(DDL_DETECTIONS)
        cur.executescript(DDL_ANNOTATIONS)

        for stmt in DDL_INDEXES:
            cur.execute(stmt)

        # -- 6. R-tree espacial sobre las dos tablas con geometría.
        for stmt in _rtree_ddl("detections"):
            cur.execute(stmt)
        for stmt in _rtree_ddl("annotations"):
            cur.execute(stmt)

        # -- 7. Registrar las tablas en gpkg_contents:
        #       - features: tablas con geometría -> aparecen como capas QGIS.
        #       - attributes: tablas tabulares puras.
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        cur.executemany(
            "INSERT INTO gpkg_contents "
            "(table_name, data_type, identifier, description, "
            " last_change, srs_id) VALUES (?, ?, ?, ?, ?, ?);",
            [
                ("sessions", "attributes", "sessions",
                 "Sesiones de trabajo de anotación", now, 0),
                ("detections", "features", "detections",
                 "Candidatos detectados por modelos ML", now, crs_epsg),
                ("annotations", "features", "annotations",
                 "Anotaciones validadas por el arqueólogo", now, crs_epsg),
            ],
        )

        # -- 8. Registrar las columnas geométricas de las tablas espaciales.
        cur.executemany(
            "INSERT INTO gpkg_geometry_columns "
            "(table_name, column_name, geometry_type_name, srs_id, z, m) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            [
                ("detections", "geom", "POLYGON", crs_epsg, 0, 0),
                ("annotations", "geom", "POLYGON", crs_epsg, 0, 0),
            ],
        )

        # -- 9. Registrar la extensión RTree en gpkg_extensions
        #       (requerido por la spec cuando hay índices espaciales).
        cur.executemany(
            "INSERT INTO gpkg_extensions "
            "(table_name, column_name, extension_name, definition, scope) "
            "VALUES (?, ?, ?, ?, ?);",
            [
                ("detections", "geom", "gpkg_rtree_index",
                 "http://www.geopackage.org/spec120/#extension_rtree",
                 "write-only"),
                ("annotations", "geom", "gpkg_rtree_index",
                 "http://www.geopackage.org/spec120/#extension_rtree",
                 "write-only"),
            ],
        )

        # -- 10. Inicializar contadores de OGR en cero.
        cur.executemany(
            "INSERT INTO gpkg_ogr_contents (table_name, feature_count) "
            "VALUES (?, ?);",
            [("detections", 0), ("annotations", 0)],
        )

        conn.commit()
    finally:
        conn.close()

    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inicializa el GeoPackage de GeoGlyph con las "
                    "tres tablas del MER (sessions, detections, annotations).",
    )
    parser.add_argument(
        "path",
        help="Ruta del archivo .gpkg a crear.",
    )
    parser.add_argument(
        "--crs",
        type=int,
        default=32719,
        choices=sorted(SUPPORTED_CRS),
        help="Código EPSG del CRS para las tablas espaciales "
             "(por defecto 32719 = UTM 19S, Atacama).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobrescribir el archivo si ya existe.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    out = init_gpkg(args.path, crs_epsg=args.crs, overwrite=args.overwrite)
    print(f"GeoPackage creado: {out}")
    print(f"  CRS:        EPSG:{args.crs}")
    print("  Tablas MER: sessions, detections, annotations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
