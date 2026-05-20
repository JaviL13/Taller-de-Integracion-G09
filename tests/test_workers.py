# -*- coding: utf-8 -*-
"""
Tests unitarios para los workers asíncronos de GeoGlyph (TIGS-S5-04).

Verifica que cada worker:
  - Tenga las señales requeridas: progress(int,int), finished, error(str).
  - Emita progress con valores crecientes que representan porcentaje.
  - Emita finished con los tipos correctos al completar exitosamente.
  - Emita error (y no finished) cuando falla.

Los tests NO requieren QGIS instalado: se mockea Qt antes de importar
los workers para poder ejecutarlos en cualquier entorno de CI.
"""

import os
import sys

import numpy as np
import pytest

# ===========================================================================
# Mock de Qt — debe instalarse ANTES de cualquier import de workers
# ===========================================================================


class _MockSignal:
    """Señal Qt mínima: rastrea emisiones y reenvía a slots conectados."""

    def __init__(self, *types):
        self.types = types
        self.emissions: list = []
        self._slots: list = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        self.emissions.append(args)
        for slot in self._slots:
            slot(*args)

    def disconnect(self, slot=None):
        if slot:
            self._slots = [s for s in self._slots if s is not slot]
        else:
            self._slots.clear()


def _pyqtSignal(*types):
    """Reemplaza pyqtSignal: devuelve un _MockSignal que actúa como descriptor."""
    return _MockSignal(*types)


class _QThread:
    """QThread mínimo que permite heredar y ejecutar run() sincrónicamente en tests."""

    # Señales built-in de QThread (compartidas a nivel de clase solo como plantilla).
    started = _MockSignal()
    finished_builtin = _MockSignal()

    def __init__(self, parent=None):
        # Cada instancia obtiene copias independientes de todas las señales
        # definidas en su clase (y superclases), evitando estado compartido.
        for klass in type(self).__mro__:
            for attr, val in vars(klass).items():
                if isinstance(val, _MockSignal):
                    object.__setattr__(self, attr, _MockSignal(*val.types))

    def start(self):
        """En tests, ejecuta run() sincrónicamente (sin threading real)."""
        self.run()

    def isRunning(self):
        return False

    def quit(self):
        pass

    def wait(self, timeout=None):
        pass

    def run(self):
        pass


# Instalar mocks en sys.modules antes de que los workers se importen.
from unittest.mock import MagicMock  # noqa: E402

_qt_core_mock = MagicMock()
_qt_core_mock.QThread = _QThread
_qt_core_mock.pyqtSignal = _pyqtSignal
_qt_core_mock.Qt = MagicMock()
_qt_gui_mock = MagicMock()

sys.modules.setdefault("qgis", MagicMock())
sys.modules.setdefault("qgis.PyQt", MagicMock())
sys.modules["qgis.PyQt.QtCore"] = _qt_core_mock
sys.modules["qgis.PyQt.QtGui"] = _qt_gui_mock
sys.modules.setdefault("qgis.core", MagicMock())
sys.modules.setdefault("qgis.gui", MagicMock())

# Agregar el directorio raíz del plugin al path para imports directos.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ===========================================================================
# Imports de workers (después de mockear Qt)
# ===========================================================================

from color_ramp_worker import ColorRampWorker  # noqa: E402
from dstretch_worker import DStretchWorker  # noqa: E402

# ===========================================================================
# Helpers
# ===========================================================================


def _collect_signals(worker):
    """Conecta los tres workers estándar y devuelve listas de captura."""
    progress_events, finished_events, error_events = [], [], []
    worker.progress.connect(lambda d, t: progress_events.append((d, t)))
    worker.error.connect(lambda msg: error_events.append(msg))
    # finished tiene firma distinta en cada worker; el caller agrega su propio slot.
    return progress_events, finished_events, error_events


def _check_progress_shape(events):
    """Verifica que los eventos de progreso tengan la forma correcta."""
    assert len(events) >= 2, "Se esperaban al menos 2 eventos de progreso (inicio y fin)"
    # El primero debe indicar inicio: done=0
    assert events[0][0] == 0, f"Primer progress debe ser (0, total), fue {events[0]}"
    # El último debe indicar finalización: done == total
    last_done, last_total = events[-1]
    assert last_done == last_total, f"Último progress debe ser (total, total), fue {events[-1]}"
    # Los valores deben ser no negativos
    for done, total in events:
        assert done >= 0 and total > 0


# ===========================================================================
# DStretchWorker
# ===========================================================================


class TestDStretchWorker:
    def test_has_required_signals(self):
        w = DStretchWorker("/fake/src.tif", "/fake/dst.tif")
        assert hasattr(w, "progress"), "Falta señal progress"
        assert hasattr(w, "finished"), "Falta señal finished"
        assert hasattr(w, "error"), "Falta señal error"

    def test_stores_init_params(self):
        w = DStretchWorker(
            "/fake/src.tif",
            "/fake/dst.tif",
            band_indices=(2, 3, 4),
            saturation_pct=2.5,
            regularization=0.01,
            bilateral_d=7,
            bilateral_sigma_color=30.0,
            bilateral_sigma_space=8.0,
        )
        assert w.src_path == "/fake/src.tif"
        assert w.dst_path == "/fake/dst.tif"
        assert w.band_indices == (2, 3, 4)
        assert w.saturation_pct == 2.5
        assert w.regularization == 0.01
        assert w.bilateral_d == 7
        assert w.bilateral_sigma_color == 30.0
        assert w.bilateral_sigma_space == 8.0

    def test_progress_callback_emits_signal(self):
        """_on_progress debe reemitir sus argumentos como señal progress."""
        w = DStretchWorker("/fake/src.tif", "/fake/dst.tif")
        captured = []
        w.progress.connect(lambda d, t: captured.append((d, t)))

        w._on_progress(0, 10)
        w._on_progress(5, 10)
        w._on_progress(10, 10)

        assert captured == [(0, 10), (5, 10), (10, 10)]

    def test_emits_error_on_nonexistent_src(self, tmp_path):
        """run() debe emitir error cuando src_path no existe."""
        dst = str(tmp_path / "out.tif")
        w = DStretchWorker("/no/existe/archivo.tif", dst)
        progress_events, _, error_events = _collect_signals(w)
        w.error.connect(lambda msg: error_events.append(msg))
        w.run()

        assert len(error_events) >= 1, "Debería emitir al menos un error"
        assert error_events[0], "El mensaje de error no debe estar vacío"

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("osgeo"),
        reason="GDAL (osgeo) no disponible",
    )
    def test_emits_finished_with_valid_raster(self, tmp_path):
        """run() emite finished(str, dict) con un raster real."""
        from osgeo import gdal

        src = str(tmp_path / "src.tif")
        dst = str(tmp_path / "dst.tif")

        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(src, 64, 64, 3, gdal.GDT_Byte)
        rng = np.random.default_rng(0)
        for i in range(1, 4):
            ds.GetRasterBand(i).WriteArray(rng.integers(0, 255, (64, 64), dtype=np.uint8))
        ds.FlushCache()
        ds = None

        finished_events = []
        w = DStretchWorker(src, dst, band_indices=(1, 2, 3))
        progress_events, _, error_events = _collect_signals(w)
        w.finished.connect(lambda path, info: finished_events.append((path, info)))
        w.run()

        assert error_events == [], f"No se esperaban errores, pero: {error_events}"
        assert len(finished_events) == 1
        out_path, info = finished_events[0]
        assert out_path == dst
        assert "elapsed_s" in info
        assert "shape" in info

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("osgeo"),
        reason="GDAL (osgeo) no disponible",
    )
    def test_progress_covers_full_range(self, tmp_path):
        """El progreso debe arrancar en 0 % y terminar en 100 %."""
        from osgeo import gdal

        src = str(tmp_path / "src.tif")
        dst = str(tmp_path / "dst.tif")
        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(src, 32, 32, 3, gdal.GDT_Byte)
        rng = np.random.default_rng(1)
        for i in range(1, 4):
            ds.GetRasterBand(i).WriteArray(rng.integers(0, 255, (32, 32), dtype=np.uint8))
        ds.FlushCache()
        ds = None

        w = DStretchWorker(src, dst)
        progress_events, _, _ = _collect_signals(w)
        w.run()

        _check_progress_shape(progress_events)


# ===========================================================================
# ColorRampWorker
# ===========================================================================


class TestColorRampWorker:
    def test_has_required_signals(self):
        w = ColorRampWorker("/fake/src.tif", band=1)
        assert hasattr(w, "progress"), "Falta señal progress"
        assert hasattr(w, "finished"), "Falta señal finished"
        assert hasattr(w, "error"), "Falta señal error"

    def test_stores_init_params(self):
        w = ColorRampWorker("/fake/src.tif", band=2, min_val=10.0, max_val=200.0)
        assert w.src_path == "/fake/src.tif"
        assert w.band == 2
        assert w._min_val == 10.0
        assert w._max_val == 200.0

    def test_min_val_none_stored_as_none(self):
        w = ColorRampWorker("/fake/src.tif", band=1)
        assert w._min_val is None
        assert w._max_val is None

    def test_uses_provided_min_max_without_reading_raster(self):
        """Si min y max son provistos, finished se emite sin leer el raster."""
        w = ColorRampWorker("/fake/no/existe.tif", band=1, min_val=5.0, max_val=100.0)
        finished_events, error_events = [], []
        w.finished.connect(lambda mn, mx: finished_events.append((mn, mx)))
        w.error.connect(lambda msg: error_events.append(msg))
        w.run()

        assert error_events == [], f"No se esperaban errores, pero: {error_events}"
        assert finished_events == [(5.0, 100.0)]

    def test_emits_progress_when_using_provided_values(self):
        """run() debe emitir progress con inicio y fin incluso con min/max provistos."""
        w = ColorRampWorker("/fake/src.tif", band=1, min_val=0.0, max_val=255.0)
        progress_events = []
        w.progress.connect(lambda d, t: progress_events.append((d, t)))
        w.run()

        _check_progress_shape(progress_events)

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("osgeo"),
        reason="GDAL (osgeo) no disponible",
    )
    def test_emits_error_on_nonexistent_raster(self):
        """run() emite error cuando el raster no existe."""
        w = ColorRampWorker("/no/existe.tif", band=1)
        error_events = []
        w.error.connect(lambda msg: error_events.append(msg))
        w.run()

        assert len(error_events) == 1
        assert error_events[0]

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("osgeo"),
        reason="GDAL (osgeo) no disponible",
    )
    def test_emits_finished_with_valid_raster(self, tmp_path):
        """run() emite finished(float, float) con min < max para un raster real."""
        from osgeo import gdal

        src = str(tmp_path / "src.tif")
        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(src, 32, 32, 1, gdal.GDT_Byte)
        rng = np.random.default_rng(42)
        ds.GetRasterBand(1).WriteArray(rng.integers(10, 200, (32, 32), dtype=np.uint8))
        ds.FlushCache()
        ds = None

        finished_events, error_events = [], []
        w = ColorRampWorker(src, band=1)
        w.finished.connect(lambda mn, mx: finished_events.append((mn, mx)))
        w.error.connect(lambda msg: error_events.append(msg))
        w.run()

        assert error_events == [], f"No se esperaban errores: {error_events}"
        assert len(finished_events) == 1
        min_val, max_val = finished_events[0]
        assert min_val < max_val, f"min ({min_val}) debe ser < max ({max_val})"

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("osgeo"),
        reason="GDAL (osgeo) no disponible",
    )
    def test_progress_covers_full_range_with_raster(self, tmp_path):
        """El progreso debe arrancar en 0 y terminar en total==total."""
        from osgeo import gdal

        src = str(tmp_path / "src.tif")
        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(src, 16, 16, 1, gdal.GDT_Byte)
        ds.GetRasterBand(1).WriteArray(np.full((16, 16), 128, dtype=np.uint8))
        ds.FlushCache()
        ds = None

        w = ColorRampWorker(src, band=1)
        progress_events = []
        w.progress.connect(lambda d, t: progress_events.append((d, t)))
        w.run()

        _check_progress_shape(progress_events)


# ===========================================================================
# Verificación estructural de workers HTTP/SAM (sin instanciar Qt real)
# ===========================================================================


class TestWorkerSignalDefinitions:
    """Verifica en el código fuente que los workers HTTP y SAM tienen progress."""

    def _read_source(self, filename):
        path = os.path.join(os.path.dirname(__file__), "..", filename)
        assert os.path.exists(path), f"Archivo no encontrado: {path}"
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_enhance_worker_has_progress_signal(self):
        src = self._read_source("http_worker.py")
        assert "progress = pyqtSignal(int, int)" in src

    def test_infer_worker_has_progress_signal(self):
        src = self._read_source("infer_worker.py")
        assert "progress = pyqtSignal(int, int)" in src

    def test_sam_worker_has_progress_signal(self):
        src = self._read_source("sam_client.py")
        assert "progress = pyqtSignal(int, int)" in src

    def test_enhance_worker_emits_progress_start(self):
        src = self._read_source("http_worker.py")
        assert "self.progress.emit(0, 1)" in src

    def test_sam_worker_emits_progress_start(self):
        src = self._read_source("sam_client.py")
        assert "self.progress.emit(0," in src

    def test_dstretch_worker_class_in_source(self):
        src = self._read_source("dstretch_worker.py")
        assert "class DStretchWorker(QThread)" in src

    def test_color_ramp_worker_class_in_source(self):
        src = self._read_source("color_ramp_worker.py")
        assert "class ColorRampWorker(QThread)" in src
