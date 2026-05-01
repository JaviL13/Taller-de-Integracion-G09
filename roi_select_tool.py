# -*- coding: utf-8 -*-
"""
roi_select_tool.py — TIGS-53

Herramienta de selección rectangular de ROI (Region Of Interest) sobre el
canvas de QGIS.

Sigue el mismo patrón de QgsMapTool ya usado por `annotation_tool.py`
(TIGS-43, PolygonDrawTool): se hereda de `QgsMapTool` y se usa un
`QgsRubberBand` para feedback visual mientras el usuario arrastra el ratón.

Diferencia con PolygonDrawTool:
  - PolygonDrawTool dibuja vértices con clics sucesivos (clic izquierdo
    agrega, clic derecho cierra).
  - Esta herramienta dibuja un rectángulo arrastrando: press → move → release.

Cuando el usuario suelta el botón, se invoca el callback `on_roi_selected`
con un `QgsRectangle` (en coordenadas del CRS del canvas) que el código
cliente puede usar para:
  1. Recortar el raster activo (ver raster_crop.py).
  2. Enviar el bbox al backend en POST /infer (ver infer_worker.py).
"""

from qgis.core import QgsGeometry, QgsPointXY, QgsRectangle, QgsWkbTypes
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor


class RectangularROITool(QgsMapTool):
    """QgsMapTool que permite seleccionar un ROI rectangular en el canvas.

    Uso desde geoglyph.py::

        self._roi_tool = RectangularROITool(canvas, on_roi_selected, iface)
        canvas.setMapTool(self._roi_tool)

    Eventos:
      - canvasPressEvent (clic izquierdo)   → registra esquina inicial.
      - canvasMoveEvent  (mientras arrastra) → actualiza la rubber band.
      - canvasReleaseEvent (suelta clic)    → finaliza y llama callback.
      - keyPressEvent (Esc)                 → cancela la selección actual.
    """

    def __init__(self, canvas, on_roi_selected, iface):
        """Inicializa la herramienta de ROI rectangular.

        Args:
            canvas: `QgsMapCanvas` sobre el que se va a dibujar.
            on_roi_selected: callback que recibe un `QgsRectangle` con el
                ROI seleccionado en coordenadas del CRS del canvas.
            iface: interfaz de QGIS (usada para `messageBar`).
        """
        super().__init__(canvas)
        # Guardamos referencias a canvas/iface/callback para usarlas en los
        # event handlers — QgsMapTool no propaga el canvas a los métodos.
        self.canvas = canvas
        self.on_roi_selected = on_roi_selected
        self.iface = iface

        # Estado interno de la selección. start_point y end_point se llenan
        # en press/move; is_selecting indica si el usuario está arrastrando
        # actualmente el rectángulo.
        self.start_point = None
        self.end_point = None
        self.is_selecting = False

        # RubberBand visual: relleno semi-transparente verde para diferenciar
        # del rojo que usa PolygonDrawTool (TIGS-43); así el usuario distingue
        # las dos herramientas si quedan rastros simultáneos en el canvas.
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(QColor(0, 200, 0, 80))
        self.rubber_band.setStrokeColor(QColor(0, 150, 0, 220))
        self.rubber_band.setWidth(2)

    # ------------------------------------------------------------------ #
    # Event handlers de QgsMapTool                                       #
    # ------------------------------------------------------------------ #

    def canvasPressEvent(self, event):
        """Inicia la selección al presionar clic izquierdo.

        El botón derecho cancela la selección en curso para mantener la
        UX consistente con otras herramientas de QGIS.
        """
        if event.button() != Qt.LeftButton:
            self._reset()
            return

        # toMapCoordinates convierte píxeles del canvas a coordenadas del
        # CRS del proyecto, que es lo que necesita el bbox para que sea
        # válido sobre el raster activo.
        self.start_point = self.toMapCoordinates(event.pos())
        self.end_point = self.start_point
        self.is_selecting = True

        # Limpiar cualquier rectángulo previo antes de empezar uno nuevo.
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

    def canvasMoveEvent(self, event):
        """Actualiza el rectángulo visual mientras el usuario arrastra."""
        if not self.is_selecting or self.start_point is None:
            return

        # Esquina opuesta al punto inicial — recalculamos en cada move
        # porque QGIS dispara este evento con alta frecuencia y queremos
        # un feedback fluido.
        self.end_point = self.toMapCoordinates(event.pos())
        self._actualizar_rubber_band()

    def canvasReleaseEvent(self, event):
        """Finaliza la selección al soltar el clic izquierdo."""
        if event.button() != Qt.LeftButton or not self.is_selecting:
            return

        self.end_point = self.toMapCoordinates(event.pos())
        self.is_selecting = False

        # Construir el QgsRectangle: normalized() garantiza que x1<=x2 e
        # y1<=y2 sin importar la dirección del arrastre (puede ser cualquiera
        # de las 4 diagonales).
        rect = QgsRectangle(self.start_point, self.end_point)
        rect.normalize()

        # Validar que la selección tenga área no nula. Un clic simple sin
        # arrastre produciría un rectángulo degenerado (ancho/alto = 0).
        if rect.width() <= 0 or rect.height() <= 0:
            self.iface.messageBar().pushMessage(
                "GeoGlyph",
                "Selección inválida: arrastra para definir un rectángulo.",
                level=1,
                duration=3,
            )
            self._reset()
            return

        # Invocar callback con el rectángulo seleccionado. La rubber band
        # se mantiene visible hasta que se desactive la herramienta — útil
        # para que el usuario vea qué área se envió al backend.
        self.on_roi_selected(rect)

    def keyPressEvent(self, event):
        """Cancela la selección actual al presionar Escape."""
        if event.key() == Qt.Key_Escape:
            self._reset()

    def deactivate(self):
        """Limpia la rubber band al desactivar la herramienta.

        QGIS llama este método cuando el usuario cambia a otra herramienta
        del canvas. Sin esto, el rectángulo verde quedaría dibujado
        permanentemente.
        """
        self._reset()
        super().deactivate()

    # ------------------------------------------------------------------ #
    # Helpers privados                                                   #
    # ------------------------------------------------------------------ #

    def _actualizar_rubber_band(self):
        """Redibuja la rubber band con el rectángulo actual.

        Construimos un polígono con las 4 esquinas porque
        QgsWkbTypes.PolygonGeometry requiere geometría poligonal (no existe
        un tipo nativo "rectángulo" en Qgs). Las esquinas se recalculan
        desde start_point y end_point.
        """
        if self.start_point is None or self.end_point is None:
            return

        x1, y1 = self.start_point.x(), self.start_point.y()
        x2, y2 = self.end_point.x(), self.end_point.y()

        # 4 esquinas en orden CCW para que el polígono sea válido.
        corners = [
            QgsPointXY(x1, y1),
            QgsPointXY(x2, y1),
            QgsPointXY(x2, y2),
            QgsPointXY(x1, y2),
        ]
        geom = QgsGeometry.fromPolygonXY([corners])

        # setToGeometry reemplaza la rubber band con la nueva geometría —
        # más simple que addPoint() iterativo y evita parpadeo en pantalla.
        self.rubber_band.setToGeometry(geom, None)

    def _reset(self):
        """Limpia el estado interno y la rubber band."""
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
