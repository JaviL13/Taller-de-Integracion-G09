# -*- coding: utf-8 -*-
"""
Worker asíncrono para calcular estadísticas de banda (min/max) fuera del hilo
principal de QGIS y preparar los datos para aplicar un Color Ramp renderer.

El único paso potencialmente lento —leer estadísticas del raster— ocurre en el
hilo secundario vía GDAL. El renderer QGIS se construye en el hilo principal al
recibir la señal finished, ya que la API de QGIS no es thread-safe.

Señales emitidas (en orden):
  progress(int, int)     – (paso_actual, total_pasos) — barra de porcentaje
  finished(float, float) – (min_val, max_val) listos para aplicar el renderer
  error(str)             – mensaje legible de error
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal


class ColorRampWorker(QThread):
    """QThread que calcula estadísticas de banda (min/max) usando GDAL.

    El resultado se emite vía señal finished para que el hilo principal
    construya el QgsSingleBandPseudoColorRenderer sin bloquear la UI.

    Signals:
        progress(int, int): (paso_actual, total_pasos).
        finished(float, float): (min_val, max_val) de la banda.
        error(str): mensaje legible para mostrar al usuario.

    Args:
        src_path: ruta al GeoTIFF fuente (o cualquier raster que GDAL pueda abrir).
        band: índice de banda 1-indexado.
        min_val: mínimo manual provisto por el usuario (None → se calcula).
        max_val: máximo manual provisto por el usuario (None → se calcula).
        parent: parent Qt (opcional).
    """

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(float, float)
    error = pyqtSignal(str)

    # Pasos que se emiten como progreso cuando hay que leer el raster:
    #   0 → inicio, 1 → raster abierto, 2 → stats leídas, 3 → listo
    _TOTAL_STEPS = 3

    def __init__(
        self,
        src_path: str,
        band: int,
        min_val=None,
        max_val=None,
        parent=None,
    ):
        super().__init__(parent)
        self.src_path = src_path
        self.band = int(band)
        self._min_val = float(min_val) if min_val is not None else None
        self._max_val = float(max_val) if max_val is not None else None

    # ------------------------------------------------------------------
    # Hilo de trabajo
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Calcula min/max de la banda en el hilo secundario."""
        self.progress.emit(0, self._TOTAL_STEPS)

        try:
            # Si el usuario ya proveyó ambos valores, los usamos directamente.
            if self._min_val is not None and self._max_val is not None:
                self.progress.emit(self._TOTAL_STEPS, self._TOTAL_STEPS)
                self.finished.emit(self._min_val, self._max_val)
                return

            # Importamos GDAL de forma diferida para que el módulo sea
            # importable en entornos de test sin osgeo instalado.
            try:
                from osgeo import gdal

                gdal.UseExceptions()
            except ImportError:
                self.error.emit(
                    "GDAL (osgeo) no está disponible en este entorno. "
                    "Instala osgeo para calcular estadísticas automáticamente, "
                    "o introduce los valores Min/Max manualmente en el panel."
                )
                return

            # Paso 1 — abrir el raster
            self.progress.emit(1, self._TOTAL_STEPS)
            ds = gdal.Open(self.src_path, gdal.GA_ReadOnly)
            if ds is None:
                self.error.emit(f"No se pudo abrir el raster: {self.src_path}")
                return

            n_bands = ds.RasterCount
            if self.band < 1 or self.band > n_bands:
                ds = None
                self.error.emit(f"Banda {self.band} fuera de rango — el raster tiene {n_bands} banda(s).")
                return

            # Paso 2 — leer estadísticas
            # GetStatistics(approx_ok, force) → (min, max, mean, stddev)
            # approx_ok=True usa overviews si están disponibles (más rápido).
            self.progress.emit(2, self._TOTAL_STEPS)
            band_obj = ds.GetRasterBand(self.band)
            stats = band_obj.GetStatistics(True, True)
            ds = None

            # Paso 3 — listo
            self.progress.emit(self._TOTAL_STEPS, self._TOTAL_STEPS)
            self.finished.emit(float(stats[0]), float(stats[1]))

        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Error calculando estadísticas de banda: {type(e).__name__}: {e}")
