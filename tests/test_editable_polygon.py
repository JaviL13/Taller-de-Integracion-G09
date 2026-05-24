# -*- coding: utf-8 -*-
"""Tests de integración del flujo máscara SAM → polígono editable (TIGS-97).

Verifican que:
  1. _on_roi_seleccionado almacena un Affine georreferenciado en _roi_transform.
  2. _on_sam_finished pasa _roi_transform a agregar_desde_mascara.
  3. Tras persistir el polígono se activa la capa de anotaciones.
  4. Se activa startEditing() sobre la capa tras insertar el polígono.
  5. Se activa la herramienta de vértices (actionVertexTool).
  6. Si agregar_desde_mascara lanza ValueError, el modo edición NO se activa.
  7. Con _roi_transform=None no se lanza excepción (degradación controlada).

Tests pure-Python — no requieren QGIS instalado.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
from rasterio.transform import from_bounds

# ── Stubs de QGIS / PyQt5 ──────────────────────────────────────────────────

for _m in [
    "qgis",
    "qgis.core",
    "qgis.PyQt",
    "qgis.PyQt.QtCore",
    "qgis.PyQt.QtGui",
    "qgis.PyQt.QtWidgets",
    "PyQt5",
    "PyQt5.QtGui",
]:
    sys.modules.setdefault(_m, MagicMock())

# ── Paquete ficticio para resolver imports relativos de geoglyph.py ─────────

_PKG = "_geogl_editable_pkg"
_PLUGIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_pkg_mod = types.ModuleType(_PKG)
_pkg_mod.__path__ = [_PLUGIN_DIR]
_pkg_mod.__package__ = _PKG
sys.modules[_PKG] = _pkg_mod

for _sub in [
    "annotation_manager",
    "annotation_state",
    "annotation_tool",
    "decorrelation_dialog",
    "geoglyph_dialog",
    "geoglyph_panel",
    "http_worker",
    "infer_worker",
    "raster_crop",
    "resources",
    "roi_select_tool",
    "sam_client",
    "color_ramp_worker",
    "dstretch_worker",
]:
    _stub = MagicMock()
    _stub.__all__ = []
    sys.modules[f"{_PKG}.{_sub}"] = _stub
    setattr(_pkg_mod, _sub, _stub)

# ── Cargar geoglyph.py como módulo del paquete ficticio ──────────────────────

_spec = importlib.util.spec_from_file_location(
    f"{_PKG}.geoglyph",
    os.path.join(_PLUGIN_DIR, "geoglyph.py"),
)
_geoglyph_mod = importlib.util.module_from_spec(_spec)
_geoglyph_mod.__package__ = _PKG
sys.modules[f"{_PKG}.geoglyph"] = _geoglyph_mod
_spec.loader.exec_module(_geoglyph_mod)

GeoGlyph = _geoglyph_mod.GeoGlyph


# ── Helper: instancia mínima ─────────────────────────────────────────────────


def _make_plugin():
    plugin = GeoGlyph.__new__(GeoGlyph)
    plugin.iface = MagicMock()
    plugin.plugin_dir = ""
    plugin.actions = []
    plugin.menu = ""
    plugin.panel = MagicMock()
    plugin._worker = None
    plugin._color_ramp_worker = None
    plugin._color_ramp_context = {}
    plugin._dstretch_dialog = None
    plugin._draw_tool = None
    plugin._annotation_manager = None
    plugin._roi_tool = None
    plugin._infer_worker = None
    plugin._sam_worker = None
    plugin._roi_transform = None
    plugin._suppress_save_handler = False
    return plugin


def _image(w=64, h=64):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _mask(w=64, h=64):
    m = np.zeros((h, w), dtype=np.uint8)
    m[10:54, 10:54] = 255
    return m


# ── Tests: _on_roi_seleccionado guarda Affine ────────────────────────────────


def test_roi_guarda_roi_transform():
    """_on_roi_seleccionado debe almacenar un Affine en _roi_transform."""
    plugin = _make_plugin()
    plugin.iface.activeLayer.return_value = MagicMock()

    crop = {
        "bbox": [500000.0, 7490000.0, 500064.0, 7490064.0],
        "pixels_w": 64,
        "pixels_h": 64,
        "image_path": "/tmp/test.tif",
        "crs_epsg": 32719,
    }

    with patch.object(_geoglyph_mod, "extract_raster_crop", return_value=crop), patch.object(
        _geoglyph_mod, "extract_raster_pixels", return_value=_image()
    ), patch.object(_geoglyph_mod, "SamWorker", return_value=MagicMock()):
        plugin._on_roi_seleccionado(MagicMock())

    assert plugin._roi_transform is not None


def test_roi_transform_georreferenciado_correctamente():
    """El Affine guardado debe corresponder al bbox devuelto por extract_raster_crop."""
    plugin = _make_plugin()
    plugin.iface.activeLayer.return_value = MagicMock()

    xmin, ymin, xmax, ymax = 500000.0, 7490000.0, 500064.0, 7490064.0
    pw, ph = 64, 64
    crop = {"bbox": [xmin, ymin, xmax, ymax], "pixels_w": pw, "pixels_h": ph, "crs_epsg": 32719, "image_path": ""}
    expected = from_bounds(xmin, ymin, xmax, ymax, pw, ph)

    with patch.object(_geoglyph_mod, "extract_raster_crop", return_value=crop), patch.object(
        _geoglyph_mod, "extract_raster_pixels", return_value=_image()
    ), patch.object(_geoglyph_mod, "SamWorker", return_value=MagicMock()):
        plugin._on_roi_seleccionado(MagicMock())

    # Comparar los 6 coeficientes del Affine
    for a, b in zip(plugin._roi_transform, expected):
        assert abs(a - b) < 1e-6, f"Coeficiente Affine incorrecto: {a} != {b}"


def test_roi_transform_none_si_extract_crop_falla():
    """Si extract_raster_crop lanza ValueError, _roi_transform no debe actualizarse."""
    plugin = _make_plugin()
    plugin.iface.activeLayer.return_value = MagicMock()
    plugin._roi_transform = None

    with patch.object(_geoglyph_mod, "extract_raster_crop", side_effect=ValueError("fuera del raster")):
        plugin._on_roi_seleccionado(MagicMock())

    assert plugin._roi_transform is None


# ── Tests: _on_sam_finished pasa transform ────────────────────────────────────


def test_sam_finished_pasa_transform_a_agregar_desde_mascara():
    """_on_sam_finished debe pasar _roi_transform al manager."""
    plugin = _make_plugin()

    transform = from_bounds(500000, 7490000, 500064, 7490064, 64, 64)
    plugin._roi_transform = transform

    mock_manager = MagicMock()
    mock_manager.layer = MagicMock()
    mock_manager.layer.isEditable.return_value = False

    with patch.object(plugin, "_get_or_create_annotation_manager", return_value=mock_manager):
        plugin._on_sam_finished(_mask(), 0.90)

    mock_manager.agregar_desde_mascara.assert_called_once()
    _, kwargs = mock_manager.agregar_desde_mascara.call_args
    assert kwargs.get("transform") is transform


def test_sam_finished_con_transform_none_no_lanza_excepcion():
    """Si _roi_transform es None, _on_sam_finished no debe fallar."""
    plugin = _make_plugin()
    plugin._roi_transform = None

    mock_manager = MagicMock()
    mock_manager.layer = MagicMock()
    mock_manager.layer.isEditable.return_value = False

    with patch.object(plugin, "_get_or_create_annotation_manager", return_value=mock_manager):
        try:
            plugin._on_sam_finished(_mask(), 0.75)
        except Exception as exc:
            raise AssertionError(f"_on_sam_finished no debe lanzar excepción con transform=None: {exc}") from exc


# ── Tests: activación de vertex editing ─────────────────────────────────────


def test_sam_finished_activa_capa_de_anotaciones():
    """Tras agregar el polígono, la capa de anotaciones debe quedar activa."""
    plugin = _make_plugin()
    plugin._roi_transform = from_bounds(0, 0, 64, 64, 64, 64)

    ann_layer = MagicMock()
    ann_layer.isEditable.return_value = False
    mock_manager = MagicMock()
    mock_manager.layer = ann_layer

    with patch.object(plugin, "_get_or_create_annotation_manager", return_value=mock_manager):
        plugin._on_sam_finished(_mask(), 0.80)

    plugin.iface.setActiveLayer.assert_called_with(ann_layer)


def test_sam_finished_llama_startEditing():
    """Tras agregar el polígono, debe activarse el modo edición en la capa."""
    plugin = _make_plugin()
    plugin._roi_transform = from_bounds(0, 0, 64, 64, 64, 64)

    ann_layer = MagicMock()
    ann_layer.isEditable.return_value = False
    mock_manager = MagicMock()
    mock_manager.layer = ann_layer

    with patch.object(plugin, "_get_or_create_annotation_manager", return_value=mock_manager):
        plugin._on_sam_finished(_mask(), 0.80)

    ann_layer.startEditing.assert_called_once()


def test_sam_finished_no_llama_startEditing_si_ya_editable():
    """Si la capa ya está en modo edición, no debe llamar startEditing de nuevo."""
    plugin = _make_plugin()
    plugin._roi_transform = from_bounds(0, 0, 64, 64, 64, 64)

    ann_layer = MagicMock()
    ann_layer.isEditable.return_value = True
    mock_manager = MagicMock()
    mock_manager.layer = ann_layer

    with patch.object(plugin, "_get_or_create_annotation_manager", return_value=mock_manager):
        plugin._on_sam_finished(_mask(), 0.80)

    ann_layer.startEditing.assert_not_called()


def test_sam_finished_activa_herramienta_de_vertices():
    """Tras agregar el polígono, debe activarse la herramienta de vértices."""
    plugin = _make_plugin()
    plugin._roi_transform = from_bounds(0, 0, 64, 64, 64, 64)

    ann_layer = MagicMock()
    ann_layer.isEditable.return_value = False
    mock_manager = MagicMock()
    mock_manager.layer = ann_layer

    with patch.object(plugin, "_get_or_create_annotation_manager", return_value=mock_manager):
        plugin._on_sam_finished(_mask(), 0.80)

    plugin.iface.actionVertexTool().trigger.assert_called()


# ── Tests: error en agregar_desde_mascara ────────────────────────────────────


def test_sam_finished_no_activa_edicion_si_agregar_falla():
    """Si agregar_desde_mascara lanza ValueError, no se debe activar edición."""
    plugin = _make_plugin()
    plugin._roi_transform = from_bounds(0, 0, 64, 64, 64, 64)

    ann_layer = MagicMock()
    mock_manager = MagicMock()
    mock_manager.layer = ann_layer
    mock_manager.agregar_desde_mascara.side_effect = ValueError("máscara vacía")

    with patch.object(plugin, "_get_or_create_annotation_manager", return_value=mock_manager):
        plugin._on_sam_finished(_mask(), 0.80)

    ann_layer.startEditing.assert_not_called()
    plugin.iface.actionVertexTool().trigger.assert_not_called()
