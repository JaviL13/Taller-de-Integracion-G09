# -*- coding: utf-8 -*-
"""Tests de persistencia del historial de notas — TIGS-87 (requieren QGIS).

Valida los criterios de aceptación del ticket usando el AnnotationManager real:
  - La tabla annotation_notes se crea al instanciar el manager.
  - Agregar una nota NO elimina las anteriores (append-only).
  - El historial se devuelve ordenado cronológicamente.
  - Cada nota captura origen, estado y score *al momento de escribirla*.
  - El historial persiste entre instancias del manager (simula reinicio QGIS).
  - Compatibilidad con API antigua (guardar_notas / leer_notas).

Estos tests REQUIEREN QGIS instalado (PyQGIS): si no lo está, se saltan
automáticamente con pytest.importorskip.
"""

import os
import sqlite3
import sys
import time

import pytest

qgis_core = pytest.importorskip("qgis.core")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)

import annotation_manager  # noqa: E402

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def qgis_app():
    app = QgsApplication([], False)
    app.initQgis()
    yield app
    app.exitQgis()


@pytest.fixture
def crs():
    return QgsCoordinateReferenceSystem("EPSG:32719")


@pytest.fixture
def gpkg_path(tmp_path):
    return str(tmp_path / "test_notes.gpkg")


@pytest.fixture
def proyecto_limpio():
    QgsProject.instance().clear()
    yield
    QgsProject.instance().clear()


def _polygon_dummy():
    pts = [
        QgsPointXY(0, 0),
        QgsPointXY(0, 10),
        QgsPointXY(10, 10),
        QgsPointXY(10, 0),
    ]
    return QgsGeometry.fromPolygonXY([pts])


# ── Criterio: la tabla se crea al instanciar el manager ──────────────────────


def test_tabla_annotation_notes_existe_tras_crear_manager(qgis_app, crs, gpkg_path, proyecto_limpio):
    """Al instanciar el AnnotationManager, annotation_notes debe existir en el GPKG."""
    annotation_manager.AnnotationManager(gpkg_path, crs)

    conn = sqlite3.connect(gpkg_path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    finally:
        conn.close()
    assert "annotation_notes" in tables


# ── Criterio: agregar nota no elimina las anteriores ─────────────────────────


def test_agregar_nota_no_elimina_anteriores(qgis_app, crs, gpkg_path, proyecto_limpio):
    """Agregar una segunda nota debe conservar la primera."""
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    feat = mgr.agregar_anotacion(_polygon_dummy())
    fid = feat.id()

    mgr.agregar_nota(fid, "primera nota")
    mgr.agregar_nota(fid, "segunda nota")

    historial = mgr.leer_historial_notas(fid)
    assert len(historial) == 2
    textos = [n["texto"] for n in historial]
    assert "primera nota" in textos
    assert "segunda nota" in textos


# ── Criterio: historial ordenado cronológicamente ────────────────────────────


def test_historial_ordenado_cronologicamente(qgis_app, crs, gpkg_path, proyecto_limpio):
    """Las notas deben devolverse ordenadas de más antigua a más reciente."""
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    feat = mgr.agregar_anotacion(_polygon_dummy())
    fid = feat.id()

    mgr.agregar_nota(fid, "nota A")
    time.sleep(0.01)
    mgr.agregar_nota(fid, "nota B")
    time.sleep(0.01)
    mgr.agregar_nota(fid, "nota C")

    historial = mgr.leer_historial_notas(fid)
    textos = [n["texto"] for n in historial]
    assert textos == ["nota A", "nota B", "nota C"]


# ── Criterio: nota captura estado y origen en el momento ─────────────────────


def test_nota_captura_estado_al_momento_de_escribir(qgis_app, crs, gpkg_path, proyecto_limpio):
    """Cada nota debe registrar el estado y origen en el que estaba la anotación
    al momento de escribirla, no el estado actual."""
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    feat = mgr.agregar_anotacion(_polygon_dummy(), origin="ml-annotation", score=0.87)
    fid = feat.id()

    # Nota mientras el polígono está en 'pending'.
    mgr.agregar_nota(fid, "revisión inicial", origen="ml-annotation", estado="pending", score=0.87)

    # Aprobamos y agregamos otra nota con el estado nuevo.
    mgr.aprobar_anotacion(fid)
    mgr.agregar_nota(fid, "aprobado por arqueólogo", origen="human-annotation", estado="approved", score=None)

    historial = mgr.leer_historial_notas(fid)
    assert len(historial) == 2
    assert historial[0]["estado"] == "pending"
    assert historial[0]["origen"] == "ml-annotation"
    assert abs(historial[0]["score"] - 0.87) < 0.001
    assert historial[1]["estado"] == "approved"
    assert historial[1]["origen"] == "human-annotation"
    assert historial[1]["score"] is None


# ── Criterio: historial persiste entre managers ───────────────────────────────


def test_historial_persiste_entre_managers(qgis_app, crs, gpkg_path, proyecto_limpio):
    """Las notas deben sobrevivir al cerrar y reabrir el manager (reinicio QGIS)."""
    mgr_a = annotation_manager.AnnotationManager(gpkg_path, crs)
    feat = mgr_a.agregar_anotacion(_polygon_dummy())
    fid = feat.id()
    mgr_a.agregar_nota(fid, "nota persistida")

    # Simular cierre de QGIS limpiando el proyecto.
    QgsProject.instance().clear()

    mgr_b = annotation_manager.AnnotationManager(gpkg_path, crs)
    historial = mgr_b.leer_historial_notas(fid)

    assert len(historial) == 1
    assert historial[0]["texto"] == "nota persistida"


# ── Criterio: guardar_notas (compat) no sobreescribe ─────────────────────────


def test_guardar_notas_compat_no_sobreescribe(qgis_app, crs, gpkg_path, proyecto_limpio):
    """guardar_notas() (API antigua) debe agregar al historial, no sobreescribir."""
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    feat = mgr.agregar_anotacion(_polygon_dummy())
    fid = feat.id()

    mgr.guardar_notas(fid, "nota via API antigua")
    mgr.guardar_notas(fid, "segunda nota via API antigua")

    historial = mgr.leer_historial_notas(fid)
    assert len(historial) == 2


# ── Criterio: leer_notas (compat) devuelve la última nota ────────────────────


def test_leer_notas_compat_devuelve_ultima(qgis_app, crs, gpkg_path, proyecto_limpio):
    """leer_notas() debe devolver el texto de la nota más reciente."""
    mgr = annotation_manager.AnnotationManager(gpkg_path, crs)
    feat = mgr.agregar_anotacion(_polygon_dummy())
    fid = feat.id()

    mgr.agregar_nota(fid, "nota vieja")
    time.sleep(0.01)
    mgr.agregar_nota(fid, "nota reciente")

    assert mgr.leer_notas(fid) == "nota reciente"
