# -*- coding: utf-8 -*-
"""Tests del nuevo flujo ROI → Realces → SAM (TIGS-87).

Verifican que:
  1. Seleccionar un ROI NO dispara SAM automáticamente.
  2. Seleccionar un ROI guarda el estado y habilita btn_ejecutar_sam.
  3. _ejecutar_sam sin ROI activo muestra mensaje de error.
  4. _ejecutar_sam con ROI activo lanza SamWorker.
  5. El botón queda deshabilitado mientras SAM está corriendo.
  6. El botón se re-habilita al terminar SAM (éxito o error).

Los tests son pure-Python y no requieren instalación de QGIS.
geoglyph.py usa imports relativos (from .xxx import ...) propios de un
paquete QGIS, por lo que se carga a través de un paquete ficticio con
importlib para que los relative imports se resuelvan contra stubs.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np

# ── 1. Stubs de QGIS / PyQt5 ─────────────────────────────────────────────────

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

# ── 2. Paquete ficticio para resolver imports relativos de geoglyph.py ────────

_PKG = "_geogl_test_pkg"
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
]:
    _stub = MagicMock()
    _stub.__all__ = []  # star-import seguro
    sys.modules[f"{_PKG}.{_sub}"] = _stub
    setattr(_pkg_mod, _sub, _stub)

# ── 3. Cargar geoglyph.py como módulo del paquete ficticio ───────────────────

_spec = importlib.util.spec_from_file_location(
    f"{_PKG}.geoglyph",
    os.path.join(_PLUGIN_DIR, "geoglyph.py"),
)
_geoglyph_mod = importlib.util.module_from_spec(_spec)
_geoglyph_mod.__package__ = _PKG
sys.modules[f"{_PKG}.geoglyph"] = _geoglyph_mod
_spec.loader.exec_module(_geoglyph_mod)

GeoGlyph = _geoglyph_mod.GeoGlyph


# ── helper: instancia mínima ──────────────────────────────────────────────────


def _make_plugin():
    plugin = GeoGlyph.__new__(GeoGlyph)
    plugin.iface = MagicMock()
    plugin.plugin_dir = ""
    plugin.actions = []
    plugin.menu = ""
    plugin.panel = MagicMock()
    plugin._worker = None
    plugin._draw_tool = None
    plugin._annotation_manager = None
    plugin._roi_tool = None
    plugin._infer_worker = None
    plugin._sam_worker = None
    plugin._roi_rect = None
    plugin._roi_image_array = None
    plugin._suppress_save_handler = False
    return plugin


def _image(w=64, h=64):
    return np.zeros((h, w, 3), dtype=np.uint8)


# ── Tests: selección del ROI no dispara SAM ───────────────────────────────────


def test_roi_no_ejecuta_sam_automaticamente():
    """_on_roi_seleccionado NO debe crear ni lanzar SamWorker."""
    plugin = _make_plugin()

    with patch.object(_geoglyph_mod, "extract_raster_crop", return_value=None), patch.object(
        _geoglyph_mod, "extract_raster_pixels", return_value=_image()
    ), patch.object(_geoglyph_mod, "SamWorker") as MockSam:
        plugin.iface.activeLayer.return_value = MagicMock()
        plugin._on_roi_seleccionado(MagicMock())

        MockSam.assert_not_called()


def test_roi_guarda_rect_e_imagen_en_estado():
    """_on_roi_seleccionado debe guardar rect e image_array como estado."""
    plugin = _make_plugin()
    rect = MagicMock()
    img = _image(32, 32)

    with patch.object(_geoglyph_mod, "extract_raster_crop", return_value=None), patch.object(
        _geoglyph_mod, "extract_raster_pixels", return_value=img
    ):
        plugin.iface.activeLayer.return_value = MagicMock()
        plugin._on_roi_seleccionado(rect)

    assert plugin._roi_rect is rect
    assert plugin._roi_image_array is img


def test_roi_habilita_boton_ejecutar_sam():
    """Después de seleccionar ROI, btn_ejecutar_sam debe quedar habilitado."""
    plugin = _make_plugin()

    with patch.object(_geoglyph_mod, "extract_raster_crop", return_value=None), patch.object(
        _geoglyph_mod, "extract_raster_pixels", return_value=_image()
    ):
        plugin.iface.activeLayer.return_value = MagicMock()
        plugin._on_roi_seleccionado(MagicMock())

    plugin.panel.btn_ejecutar_sam.setEnabled.assert_called_with(True)


# ── Tests: _ejecutar_sam ─────────────────────────────────────────────────────


def test_ejecutar_sam_sin_roi_muestra_mensaje_de_error():
    """Sin ROI activo, _ejecutar_sam debe emitir un mensaje de advertencia."""
    plugin = _make_plugin()
    plugin._roi_image_array = None

    plugin._ejecutar_sam()

    plugin.iface.messageBar().pushMessage.assert_called_once()
    # El mensaje debe mencionar "ROI"
    call_args = plugin.iface.messageBar().pushMessage.call_args
    all_args = str(call_args)
    assert "ROI" in all_args


def test_ejecutar_sam_con_roi_lanza_worker():
    """Con ROI activo, _ejecutar_sam debe crear y lanzar SamWorker."""
    plugin = _make_plugin()
    plugin._roi_image_array = _image()

    with patch.object(_geoglyph_mod, "SamWorker") as MockSam:
        worker = MagicMock()
        MockSam.return_value = worker

        plugin._ejecutar_sam()

        MockSam.assert_called_once()
        worker.start.assert_called_once()


def test_boton_sam_deshabilitado_durante_ejecucion():
    """Al lanzar SAM, btn_ejecutar_sam debe deshabilitarse antes de start()."""
    plugin = _make_plugin()
    plugin._roi_image_array = _image()

    disable_calls = []

    def track_enabled(val):
        disable_calls.append(val)

    plugin.panel.btn_ejecutar_sam.setEnabled.side_effect = track_enabled

    with patch.object(_geoglyph_mod, "SamWorker", return_value=MagicMock()):
        plugin._ejecutar_sam()

    assert False in disable_calls, "btn_ejecutar_sam nunca se deshabilitó"


# ── Tests: callbacks post-SAM ────────────────────────────────────────────────


def test_boton_sam_rehabilitado_tras_sam_finished():
    """_on_sam_finished re-habilita btn_ejecutar_sam cuando hay ROI activo."""
    plugin = _make_plugin()
    plugin._roi_image_array = _image()

    mask = np.zeros((64, 64), dtype=np.uint8)

    with patch.object(plugin, "_get_or_create_annotation_manager", return_value=MagicMock()):
        plugin._on_sam_finished(mask, 0.85)

    calls = [c.args[0] for c in plugin.panel.btn_ejecutar_sam.setEnabled.call_args_list]
    assert True in calls, "btn_ejecutar_sam nunca se re-habilitó tras SAM exitoso"


def test_boton_sam_rehabilitado_tras_sam_error():
    """_on_sam_error re-habilita btn_ejecutar_sam cuando hay ROI activo."""
    plugin = _make_plugin()
    plugin._roi_image_array = _image()

    plugin._on_sam_error("Backend no disponible")

    calls = [c.args[0] for c in plugin.panel.btn_ejecutar_sam.setEnabled.call_args_list]
    assert True in calls, "btn_ejecutar_sam nunca se re-habilitó tras error de SAM"
