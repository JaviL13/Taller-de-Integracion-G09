# -*- coding: utf-8 -*-
"""
Worker asíncrono para ejecutar Decorrelation Stretch (DStretch) fuera del hilo
principal de QGIS.

DStretchWorker envuelve decorrelation_stretch() en un QThread, convirtiendo el
callback progress_cb en una señal Qt thread-safe compatible con la barra de
progreso del DecorrelationStretchDialog.

Señales emitidas (en orden):
  progress(int, int)  – (tiles_procesados, total_tiles) en modo tiled;
                        (0, 1) → (1, 1) en modo in-memory
  finished(str, dict) – (ruta_salida, estadísticas) al completar
  error(str)          – mensaje legible de error si falla
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal

try:
    from .decorrelation_stretch import decorrelation_stretch
except ImportError:
    # Fallback para entornos de test donde el módulo se importa directamente.
    from decorrelation_stretch import decorrelation_stretch  # type: ignore[no-redef]


class DStretchWorker(QThread):
    """QThread que ejecuta decorrelation_stretch() sin bloquear la UI de QGIS.

    Parámetros idénticos a decorrelation_stretch(), salvo que el resultado se
    entrega mediante señales en vez de return.

    Signals:
        progress(int, int): (tiles_procesados, total_tiles).
        finished(str, dict): (ruta_salida, estadísticas).
        error(str): mensaje de error legible.

    Args:
        src_path: ruta al GeoTIFF de entrada.
        dst_path: ruta al GeoTIFF de salida.
        band_indices: tupla de 3 enteros 1-indexados para el PCA.
        saturation_pct: porcentaje de saturación final (0–10).
        window: (xoff, yoff, xsize, ysize) o None para imagen completa.
        regularization: amortiguación de ruido en el PCA (0–1).
        bilateral_d: diámetro del filtro bilateral (0 = desactivado).
        bilateral_sigma_color: σ de color del filtro bilateral.
        bilateral_sigma_space: σ espacial del filtro bilateral.
        parent: parent Qt (opcional).
    """

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(str, dict)
    error = pyqtSignal(str)

    def __init__(
        self,
        src_path: str,
        dst_path: str,
        band_indices=(1, 2, 3),
        saturation_pct: float = 1.0,
        window=None,
        regularization: float = 0.0,
        bilateral_d: int = 0,
        bilateral_sigma_color: float = 25.0,
        bilateral_sigma_space: float = 7.0,
        parent=None,
    ):
        super().__init__(parent)
        self.src_path = src_path
        self.dst_path = dst_path
        self.band_indices = tuple(band_indices)
        self.saturation_pct = float(saturation_pct)
        self.window = window
        self.regularization = float(regularization)
        self.bilateral_d = int(bilateral_d)
        self.bilateral_sigma_color = float(bilateral_sigma_color)
        self.bilateral_sigma_space = float(bilateral_sigma_space)

    # ------------------------------------------------------------------
    # Callback de progreso → señal Qt
    # ------------------------------------------------------------------

    def _on_progress(self, done: int, total: int) -> None:
        """Convierte el callback de decorrelation_stretch en señal Qt.

        Se llama desde el hilo de trabajo. pyqtSignal.emit() es thread-safe
        en Qt, por lo que esta llamada es segura sin locks adicionales.
        """
        self.progress.emit(done, total)

    # ------------------------------------------------------------------
    # Hilo de trabajo
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Ejecuta decorrelation_stretch() y emite las señales correspondientes."""
        # Progreso inicial — modo in-memory no emite tiles, así que señalamos
        # manualmente el inicio para que la barra de progreso arranque en 0 %.
        self.progress.emit(0, 1)
        try:
            info = decorrelation_stretch(
                src_path=self.src_path,
                dst_path=self.dst_path,
                band_indices=self.band_indices,
                saturation_pct=self.saturation_pct,
                window=self.window,
                regularization=self.regularization,
                bilateral_d=self.bilateral_d,
                bilateral_sigma_color=self.bilateral_sigma_color,
                bilateral_sigma_space=self.bilateral_sigma_space,
                progress_cb=self._on_progress,
            )
            # En modo in-memory el callback nunca se llama, así que cerramos
            # la barra aquí para no dejarla atascada al 0 %.
            self.progress.emit(1, 1)
            self.finished.emit(info["output"], info)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"{type(e).__name__}: {e}")
