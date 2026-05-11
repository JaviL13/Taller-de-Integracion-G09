# -*- coding: utf-8 -*-
"""Tests de persistencia del AnnotationManager (TIGS-65).

Valida los criterios de aceptación del ticket de persistencia:
  - El polígono aparece como feature en la capa GeoPackage tras aprobar.
  - El rechazado también se guarda con estado 'rejected'.
  - Persiste al cerrar y reabrir QGIS (simulado: instanciar dos managers
    distintos sobre el mismo .gpkg).
  - El GeoPackage se crea solo si no existe (no se sobreescribe).

Estos tests REQUIEREN QGIS instalado (PyQGIS): si no lo está, se saltan
con pytest.importorskip. La validación final del contenido del .gpkg se
hace con sqlite3 puro, sin depender de QGIS, para evitar leer el archivo
'a través de la propia capa que estamos testeando'.
"""

import os
import sqlite3
import sys
import time

import pytest

# El AnnotationManager y todo PyQGIS requieren QGIS instalado. En CI no
# está disponible, así que estos tests se saltan automáticamente.
qgis_core = pytest.importorskip("qgis.core")

# Permitir importar annotation_manager.py como módulo top-level.
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)

import annotation_manager  # noqa: E402
from annotation_state import AnnotationState  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def qgis_app():
    """Inicializa QgsApplication una sola vez para toda la sesión de tests.

    Sin esto, cualquier llamada a QgsVectorLayer / QgsVectorFileWriter se
    cuelga o crashea porque PyQGIS necesita un QApplication corriendo.
    """
    app = QgsApplication([], False)
    app.initQgis()
    yield app
    app.exitQgis()


@pytest.fixture
def crs():
    """CRS UTM 19S (zona donde está Atacama, default del proyecto)."""
    return QgsCoordinateReferenceSystem("EPSG:32719")


@pytest.fixture
def gpkg_path(tmp_path):
    """Ruta a un .gpkg en un tmp dir (no existe todavía)."""
    return str(tmp_path / "test_annotations.gpkg")


@pytest.fixture
def proyecto_limpio():
    """Limpia el proyecto QGIS entre tests para que las capas no se
    crucen entre casos (el AnnotationManager reutiliza la capa si ya
    está cargada, lo cual contaminaría tests si no limpiamos)."""
    QgsProject.instance().clear()
    yield
    QgsProject.instance().clear()


def _polygon_dummy():
    """Genera un polígono simple para usar como feature de prueba."""
    pts = [
        QgsPointXY(0, 0),
        QgsPointXY(0, 10),
        QgsPointXY(10, 10),
        QgsPointXY(10, 0),
    ]
    return QgsGeometry.fromPolygonXY([pts])


def _leer_status_con_sqlite(gpkg_path):
    """Lee la columna status de annotations usando sqlite3 directo
    (independiente de QGIS, valida que el archivo realmente persistió)."""
    conn = sqlite3.connect(gpkg_path)
    try:
        rows = conn.execute(
            "SELECT fid, status FROM annotations ORDER BY fid;"
        ).fetchall()
    finally:
        conn.close()
    return rows


# ── Criterio: el GeoPackage se crea solo si no existe ────────────────────

def test_crea_archivo_si_no_existe(qgis_app, crs, gpkg_path, proyecto_limpio):
    """Si annotations.gpkg no existe, el manager debe crearlo con la
    tabla 'annotations' lista."""
    assert not os.path.exists(gpkg_path)

    annotation_manager.AnnotationManager(gpkg_path, crs)

    assert os.path.exists(gpkg_path)
    # La tabla 'annotations' debe estar declarada en gpkg_contents
    # (es lo que hace QGIS para reconocerla como capa).
    conn = sqlite3.connect(gpkg_path)
    try:
        rows = conn.execute(
            "SELECT table_name FROM gpkg_contents "
            "WHERE table_name='annotations';"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [("annotations",)]


def test_no_sobreescribe_archivo_existente(
    qgis_app, crs, gpkg_path, proyecto_limpio
):
    """Si el .gpkg ya existe, instanciar otro manager NO debe regenerarlo
    (mtime y contenido se preservan)."""
    # Manager A: crea el archivo y agrega un feature.
    mgr_a = annotation_manager.AnnotationManager(gpkg_path, crs)
    mgr_a.agregar_anotacion(_polygon_dummy())
    rows_a = _leer_status_con_sqlite(gpkg_path)
    mtime_inicial = os.path.getmtime(gpkg_path)

    # Limpiar el proyecto para forzar al manager B a recargar la capa
    # desde disco en lugar de reutilizar la cargada en memoria.
    QgsProject.instance().clear()
    time.sleep(0.05)  # garantizar que un mtime nuevo sería distinguible

    # Manager B: solo abre el archivo, no escribe nada.
    annotation_manager.AnnotationManager(gpkg_path, crs)

    # El contenido debe ser idéntico (mismo número de filas y status).
    rows_b = _leer_status_con_sqlite(gpkg_path)
    assert rows_a == rows_b
    # mtime no debió cambiar (no hubo escritura).
    assert os.path.getmtime(gpkg_path) == mtime_inicial


# ── Criterio: pending al crear, persiste al GPKG ─────────────────────────

def test_agregar_anotacion_persiste_como_pending(
    qgis_app, crs, gpkg_path, proyecto_limpio
):
    """Tras agregar_anotacion, sqlite3 debe ver una fila con status=pending."""
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    mgr.agregar_anotacion(_polygon_dummy())

    rows = _leer_status_con_sqlite(gpkg_path)
    assert len(rows) == 1
    assert rows[0][1] == AnnotationState.PENDING.value


# ── Criterio: aprobar persiste con status='approved' ─────────────────────

def test_aprobar_persiste_status_approved(
    qgis_app, crs, gpkg_path, proyecto_limpio
):
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    feat = mgr.agregar_anotacion(_polygon_dummy())

    ok = mgr.aprobar_anotacion(feat.id())
    assert ok is True

    # Validación independiente de QGIS: el archivo en disco tiene status=approved.
    rows = _leer_status_con_sqlite(gpkg_path)
    assert rows == [(feat.id(), AnnotationState.APPROVED.value)]


# ── Criterio: rechazar persiste con status='rejected' ────────────────────

def test_rechazar_persiste_status_rejected(
    qgis_app, crs, gpkg_path, proyecto_limpio
):
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    feat = mgr.agregar_anotacion(_polygon_dummy())

    ok = mgr.rechazar_anotacion(feat.id())
    assert ok is True

    rows = _leer_status_con_sqlite(gpkg_path)
    assert rows == [(feat.id(), AnnotationState.REJECTED.value)]


# ── Criterio: persiste al cerrar y reabrir QGIS ──────────────────────────

def test_features_persisten_entre_managers(
    qgis_app, crs, gpkg_path, proyecto_limpio
):
    """Manager A agrega 3 polígonos (uno aprobado, uno rechazado, uno
    pending). Manager B nuevo (sobre el mismo .gpkg) debe verlos todos
    con sus estados intactos. Esto simula cerrar y reabrir QGIS."""
    # Sesión 1.
    mgr_a = annotation_manager.AnnotationManager(gpkg_path, crs)
    f1 = mgr_a.agregar_anotacion(_polygon_dummy())
    f2 = mgr_a.agregar_anotacion(_polygon_dummy())
    mgr_a.aprobar_anotacion(f1.id())
    mgr_a.rechazar_anotacion(f2.id())

    # Limpiar el proyecto para forzar a que mgr_b cargue la capa de cero.
    QgsProject.instance().clear()

    # Sesión 2: nuevo manager, mismo path → debe ver los 3 features.
    mgr_b = annotation_manager.AnnotationManager(gpkg_path, crs)
    assert mgr_b.layer.featureCount() == 3

    estados = sorted(
        f.attribute("status") for f in mgr_b.layer.getFeatures()
    )
    assert estados == ["approved", "pending", "rejected"]


# ── Estado intermedio: cambios sucesivos persisten correctamente ─────────

def test_aprobar_luego_rechazar_persiste_ultimo_estado(
    qgis_app, crs, gpkg_path, proyecto_limpio
):
    """Si aprobamos y luego rechazamos, el archivo debe mostrar el
    último estado (rejected). Verifica que no hay caches que dejen
    versiones obsoletas en disco."""
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    feat = mgr.agregar_anotacion(_polygon_dummy())
    mgr.aprobar_anotacion(feat.id())
    mgr.rechazar_anotacion(feat.id())

    rows = _leer_status_con_sqlite(gpkg_path)
    assert rows[0][1] == AnnotationState.REJECTED.value


# ── La capa expuesta es GPKG-backed, no de memoria ───────────────────────

def test_capa_es_gpkg_backed_no_memory(
    qgis_app, crs, gpkg_path, proyecto_limpio
):
    """Asegura que el provider sea 'ogr' (GPKG-backed), no 'memory'.
    Si fuera 'memory', los cambios no llegarían al disco — la causa
    raíz del bug que este ticket arregla."""
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    assert mgr.layer.providerType() == "ogr"
    # El source de un layer ogr-gpkg incluye la ruta del archivo.
    assert gpkg_path in mgr.layer.source()
