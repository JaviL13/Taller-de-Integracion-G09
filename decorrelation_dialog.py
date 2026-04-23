# coding: utf-8
"""
Diálogo Qt para lanzar el Decorrelation Stretch desde QGIS.

Permite al usuario:
  - Elegir la capa raster ya cargada en el proyecto (o abrir una nueva desde disco).
  - Elegir qué 3 bandas del raster alimentan el PCA.
  - Ajustar el porcentaje de saturación final (default 1%).
  - Elegir la ruta de salida (o usar un archivo temporal).

Al aceptar, aplica el algoritmo y agrega el resultado como nueva capa
georreferenciada al proyecto activo.
"""

from __future__ import annotations

import os
import tempfile
import time
import traceback

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsMapLayerProxyModel,
    QgsCoordinateTransform,
)
from qgis.gui import QgsMapLayerComboBox

from .decorrelation_stretch import decorrelation_stretch


class DecorrelationStretchDialog(QtWidgets.QDialog):
    """Diálogo modal para configurar y ejecutar el decorrelation stretch."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Decorrelation Stretch (PCA)")
        self.setMinimumWidth(440)

        outer = QtWidgets.QVBoxLayout(self)

        # ---- Capa de entrada ------------------------------------------------
        layer_group = QtWidgets.QGroupBox("Capa raster de entrada")
        layer_layout = QtWidgets.QVBoxLayout(layer_group)

        self.layer_combo = QgsMapLayerComboBox(self)
        self.layer_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)
        layer_layout.addWidget(self.layer_combo)

        self.btn_abrir_tiff = QtWidgets.QPushButton(
            "… o abrir GeoTIFF desde disco")
        self.btn_abrir_tiff.clicked.connect(self._open_geotiff)
        layer_layout.addWidget(self.btn_abrir_tiff)

        outer.addWidget(layer_group)

        # ---- Selector de bandas --------------------------------------------
        band_group = QtWidgets.QGroupBox("Bandas de entrada para el PCA")
        band_layout = QtWidgets.QGridLayout(band_group)
        band_layout.addWidget(QtWidgets.QLabel("Canal 1:"), 0, 0)
        band_layout.addWidget(QtWidgets.QLabel("Canal 2:"), 1, 0)
        band_layout.addWidget(QtWidgets.QLabel("Canal 3:"), 2, 0)
        self.band_combos = [
            QtWidgets.QComboBox(),
            QtWidgets.QComboBox(),
            QtWidgets.QComboBox(),
        ]
        for i, c in enumerate(self.band_combos):
            band_layout.addWidget(c, i, 1)
        outer.addWidget(band_group)

        # ---- Región a procesar ---------------------------------------------
        extent_group = QtWidgets.QGroupBox("Región a procesar")
        extent_layout = QtWidgets.QVBoxLayout(extent_group)
        self.extent_combo = QtWidgets.QComboBox()
        self.extent_combo.addItem("Vista actual del mapa (rápido)", "canvas")
        self.extent_combo.addItem(
            "Raster completo (procesamiento por tiles)", "full")
        self.extent_combo.setToolTip(
            "«Vista actual» procesa sólo la región visible en el lienzo de QGIS — "
            "ideal para iteración rápida.\n"
            "«Raster completo» procesa toda la imagen en teselas; la memoria "
            "queda acotada, así que funciona sobre ortomosaicos grandes.")
        extent_layout.addWidget(self.extent_combo)
        self.extent_info_lbl = QtWidgets.QLabel("")
        self.extent_info_lbl.setStyleSheet("color: #666; font-size: 11px;")
        extent_layout.addWidget(self.extent_info_lbl)
        outer.addWidget(extent_group)

        # ---- Parámetros ----------------------------------------------------
        params_group = QtWidgets.QGroupBox("Parámetros")
        params_layout = QtWidgets.QFormLayout(params_group)

        self.sat_spin = QtWidgets.QDoubleSpinBox()
        self.sat_spin.setRange(0.0, 10.0)
        self.sat_spin.setDecimals(2)
        self.sat_spin.setSingleStep(0.5)
        self.sat_spin.setValue(1.0)
        self.sat_spin.setToolTip(
            "Recorte por percentil en el estiramiento final. "
            "Valores típicos: 0.5 – 2.0. Un valor de 0 desactiva el recorte."
        )
        params_layout.addRow("Saturación (%):", self.sat_spin)

        outer.addWidget(params_group)

        # ---- Reducción de ruido --------------------------------------------
        # Dos mitigaciones para el "speckle" de colores en zonas planas:
        #  1. regularización del PCA (limita la amplificación de ejes pequeños)
        #  2. filtro bilateral post-procesamiento (suaviza conservando bordes)
        # Ambas son opcionales y se pueden combinar.
        noise_group = QtWidgets.QGroupBox("Reducción de ruido")
        noise_layout = QtWidgets.QFormLayout(noise_group)

        self.reg_spin = QtWidgets.QDoubleSpinBox()
        self.reg_spin.setRange(0.0, 5.0)
        self.reg_spin.setDecimals(2)
        self.reg_spin.setSingleStep(0.5)
        # default 1 % → mitigación suave sin perder detalle
        self.reg_spin.setValue(1.0)
        self.reg_spin.setSuffix(" %")
        self.reg_spin.setToolTip(
            "Regularización del PCA. Acota la amplificación de los ejes con "
            "poca varianza (donde vive el ruido del sensor). Valores típicos: "
            "0.5 – 2 %. 0 = sin regularización (dstretch canónico, más ruido "
            "en zonas planas)."
        )
        noise_layout.addRow("Suavizado PCA:", self.reg_spin)

        self.bilateral_combo = QtWidgets.QComboBox()
        # Cada preset es (label, d, sigma_color, sigma_space). d=0 desactiva.
        # Tuneados para ortofotos de drone: kernels chicos para no borronear
        # geoglifos pequeños, sigma_color moderado para preservar transiciones.
        self.bilateral_combo.addItem("Desactivado", (0, 0.0, 0.0))
        self.bilateral_combo.addItem("Suave", (5, 15.0, 5.0))
        self.bilateral_combo.addItem("Medio", (7, 25.0, 7.0))
        self.bilateral_combo.addItem("Fuerte", (9, 40.0, 9.0))
        self.bilateral_combo.setCurrentIndex(0)  # default: sin filtro
        self.bilateral_combo.setToolTip(
            "Filtro bilateral aplicado después del dstretch. Suaviza zonas "
            "planas conservando los bordes — elimina el ‘rainbow noise’ sin "
            "borronear los geoglifos.\n\n"
            "Usa opencv-python si está instalado (rápido). Si no, usa un "
            "fallback en numpy puro (más lento pero funciona igual)."
        )
        noise_layout.addRow("Filtro bilateral:", self.bilateral_combo)

        outer.addWidget(noise_group)

        # ---- Salida --------------------------------------------------------
        out_group = QtWidgets.QGroupBox("Archivo de salida")
        out_layout = QtWidgets.QHBoxLayout(out_group)
        self.out_edit = QtWidgets.QLineEdit()
        self.out_edit.setPlaceholderText("(se generará un archivo temporal)")
        out_layout.addWidget(self.out_edit)
        browse_btn = QtWidgets.QPushButton("…")
        browse_btn.setFixedWidth(32)
        browse_btn.clicked.connect(self._browse_output)
        out_layout.addWidget(browse_btn)
        outer.addWidget(out_group)

        # ---- Barra de estado ----------------------------------------------
        self.status_lbl = QtWidgets.QLabel(" ")
        self.status_lbl.setStyleSheet("color: #555;")
        outer.addWidget(self.status_lbl)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        # ---- Botones -------------------------------------------------------
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Aplicar")
        buttons.accepted.connect(self._run_stretch)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # Señales
        self.layer_combo.layerChanged.connect(self._on_layer_changed)
        self.extent_combo.currentIndexChanged.connect(self._update_extent_info)
        self._on_layer_changed(self.layer_combo.currentLayer())

    # -- helpers ------------------------------------------------------------

    def _on_layer_changed(self, layer):
        self._populate_bands(layer)
        self._update_extent_info()

    def _compute_window(self, layer):
        """Calcula la ventana (xoff, yoff, xsize, ysize) en píxeles del raster
        a partir de la opción elegida en extent_combo. Devuelve None para capa
        completa, o una tupla de 4 enteros."""
        mode = self.extent_combo.currentData()
        if mode == "full":
            return None

        canvas = self.iface.mapCanvas()
        map_extent = canvas.extent()
        canvas_crs = canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs != layer_crs:
            xform = QgsCoordinateTransform(
                canvas_crs, layer_crs, QgsProject.instance()
            )
            map_extent = xform.transformBoundingBox(map_extent)

        layer_extent = layer.extent()
        inter = map_extent.intersect(layer_extent)
        if inter.isEmpty():
            raise RuntimeError(
                "La vista del mapa no se superpone con la extensión del raster. "
                "Centra el mapa sobre la imagen antes de aplicar.")

        raster_w = layer.width()
        raster_h = layer.height()
        if raster_w <= 0 or raster_h <= 0:
            return None

        px_per_x = raster_w / layer_extent.width()
        px_per_y = raster_h / layer_extent.height()

        xoff = int((inter.xMinimum() - layer_extent.xMinimum()) * px_per_x)
        yoff = int((layer_extent.yMaximum() - inter.yMaximum()) * px_per_y)
        xsize = int(round(inter.width() * px_per_x))
        ysize = int(round(inter.height() * px_per_y))

        xoff = max(0, min(xoff, raster_w - 1))
        yoff = max(0, min(yoff, raster_h - 1))
        xsize = max(1, min(xsize, raster_w - xoff))
        ysize = max(1, min(ysize, raster_h - yoff))
        return (xoff, yoff, xsize, ysize)

    def _update_extent_info(self, *args):
        """Muestra el tamaño estimado de la región y el modo (memoria o tiled)."""
        layer = self.layer_combo.currentLayer()
        if layer is None or not isinstance(layer, QgsRasterLayer):
            self.extent_info_lbl.setText("")
            return
        try:
            w = self._compute_window(layer)
        except Exception as e:
            self.extent_info_lbl.setText(str(e))
            return
        if w is None:
            total = layer.width() * layer.height()
            label = f"Raster completo: {layer.width()}×{layer.height()} px"
        else:
            xoff, yoff, xsize, ysize = w
            total = xsize * ysize
            label = f"Ventana: {xsize}×{ysize} px"
        mpx = total / 1e6
        mode = "memoria (una pasada)" if total <= 16_000_000 else "tiled (2 pasadas, por teselas)"
        self.extent_info_lbl.setText(f"{label} — {mpx:.1f} Mpx · modo: {mode}")

    def _populate_bands(self, layer):
        if layer is None or not isinstance(layer, QgsRasterLayer):
            for c in self.band_combos:
                c.clear()
            return
        n = layer.bandCount()
        items = []
        for i in range(1, n + 1):
            try:
                name = layer.bandName(i)
            except Exception:
                name = f"Banda {i}"
            items.append(f"{i}: {name}")
        for i, combo in enumerate(self.band_combos):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            default_idx = i if i < n else n - 1
            combo.setCurrentIndex(default_idx)
            combo.blockSignals(False)

    def _open_geotiff(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Seleccionar GeoTIFF", "", "GeoTIFF (*.tif *.tiff)"
        )
        if not file_path:
            return
        layer_name = os.path.splitext(os.path.basename(file_path))[0]
        layer = QgsRasterLayer(file_path, layer_name)
        if not layer.isValid():
            QtWidgets.QMessageBox.critical(
                self, "Error", f"No se pudo cargar el archivo:\n{file_path}"
            )
            return
        QgsProject.instance().addMapLayer(layer)
        self.layer_combo.setLayer(layer)

    def _browse_output(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Guardar resultado", "", "GeoTIFF (*.tif *.tiff)"
        )
        if path:
            if not path.lower().endswith((".tif", ".tiff")):
                path += ".tif"
            self.out_edit.setText(path)

    # -- ejecución ----------------------------------------------------------

    def _run_stretch(self):
        layer = self.layer_combo.currentLayer()
        if layer is None or not isinstance(layer, QgsRasterLayer):
            QtWidgets.QMessageBox.warning(
                self, "Falta capa", "Selecciona una capa raster de entrada."
            )
            return

        src = layer.source()
        # Extrae índices 1-indexados desde el texto "N: nombre"
        try:
            band_indices = tuple(
                int(c.currentText().split(":", 1)[0]) for c in self.band_combos
            )
        except ValueError:
            QtWidgets.QMessageBox.critical(
                self, "Error", "No se pudieron leer los índices de banda."
            )
            return

        if len(set(band_indices)) < 3:
            resp = QtWidgets.QMessageBox.question(
                self,
                "Bandas repetidas",
                "Seleccionaste bandas repetidas. El PCA será degenerado.\n"
                "¿Deseas continuar de todas formas?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if resp != QtWidgets.QMessageBox.Yes:
                return

        # Resolver ventana a procesar
        try:
            window = self._compute_window(layer)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Región inválida", str(e))
            return

        out = self.out_edit.text().strip()
        if not out:
            fd, out = tempfile.mkstemp(
                suffix="_dstretch.tif", prefix="geoglyph_")
            os.close(fd)

        # UI en modo "procesando"
        self.status_lbl.setText(
            "Procesando… (esto puede tardar unos segundos)")
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.setCursor(Qt.WaitCursor)
        QtWidgets.QApplication.processEvents()

        def _on_progress(done, total):
            # Llamado desde el bucle de tiles. Actualizamos la barra y
            # dejamos que Qt procese eventos para que la UI no se congele.
            pct = int(100 * done / max(total, 1))
            self.progress.setValue(pct)
            self.status_lbl.setText(
                f"Procesando tile {done}/{total} ({pct}%)…"
            )
            QtWidgets.QApplication.processEvents()

        # Parámetros de reducción de ruido. El spin está en porcentaje (0–5)
        # y la API espera fracción (0–1), así que dividimos por 100.
        regularization = float(self.reg_spin.value()) / 100.0
        bilateral_d, bilateral_sigma_color, bilateral_sigma_space = (
            self.bilateral_combo.currentData()
        )

        t0 = time.perf_counter()
        try:
            info = decorrelation_stretch(
                src_path=src,
                dst_path=out,
                band_indices=band_indices,
                saturation_pct=float(self.sat_spin.value()),
                window=window,
                regularization=regularization,
                bilateral_d=int(bilateral_d),
                bilateral_sigma_color=float(bilateral_sigma_color),
                bilateral_sigma_space=float(bilateral_sigma_space),
                progress_cb=_on_progress,
            )
        except Exception as e:
            self.unsetCursor()
            self.status_lbl.setText("")
            self.progress.setVisible(False)
            QtWidgets.QMessageBox.critical(
                self,
                "Error al aplicar decorrelation stretch",
                f"{e}\n\n{traceback.format_exc()}",
            )
            return

        elapsed = time.perf_counter() - t0
        self.unsetCursor()
        self.progress.setVisible(False)

        # Carga el resultado como nueva capa georreferenciada
        base = os.path.splitext(os.path.basename(src))[0]
        bi = band_indices
        layer_name = f"{base}_dstretch_{bi[0]}{bi[1]}{bi[2]}"
        new_layer = QgsRasterLayer(out, layer_name)
        if not new_layer.isValid():
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Se generó el archivo pero QGIS no lo pudo cargar como capa:\n{out}",
            )
            return
        QgsProject.instance().addMapLayer(new_layer)

        self.status_lbl.setText(
            f"Listo: «{layer_name}» ({elapsed:.2f} s, "
            f"{info['shape'][0]}×{info['shape'][1]} px)"
        )
        self.iface.messageBar().pushSuccess(
            "GeoGlyph",
            f"Decorrelation stretch aplicado en {elapsed:.2f} s — capa: {layer_name}",
        )
        self.accept()
