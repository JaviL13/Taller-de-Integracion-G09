# Esta herramiento permite dibujar los polígonos dentro de QGIS

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
# Con esto se pueden sontruir las geométrias con los clics del mouse
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.core import QgsWkbTypes, QgsPointXY, QgsGeometry


class PolygonDrawTool(QgsMapTool):

    # Se puede dibujar un polígono al presionar sobre el canvas
    # Botón derecho del mouse agrega vértice
    # Botón izquierdo del mouse cierra y guerda el polígono
    # Con Esc se canela el dibujo

    def __init__(self, canvas, on_polygon_drawn, iface):
        super().__init__(canvas)
        self.canvas = canvas  # Este es el canvas sobre el que se dibuja
        # Función que recibre un QgsGeometry cuando se completa el polígono
        self.on_polygon_drawn = on_polygon_drawn
        self.iface = iface
        self.points = []  # lista de QgsPointXY que el usuario va haciendo clic

        # RubberBand es una línea visual que se dibuja mientras el usuario hace
        # clic
        self.rubber_band = QgsRubberBand(
            self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(
            QColor(255, 0, 0, 100))  # color rojo por ahora
        self.rubber_band.setWidth(2)

    def canvasPressEvent(self, event):
        # Se usa cuando el usuario hace click en el mapa
        # convierte píxeles a coordenadas reales
        point = self.toMapCoordinates(event.pos())

        if event.button() == Qt.LeftButton:
            # Con el botón izquierdo se agrega un punto al polígono
            self.points.append(QgsPointXY(point))
            self.rubber_band.addPoint(QgsPointXY(point), True)

        elif event.button() == Qt.RightButton:
            # Con el otón derecho se cierra el polígono
            if len(self.points) >= 3:  # Solo se cierra si tiene minimo 3 puntos
                self._finalizar_poligono()
            else:
                self.iface.messageBar().pushMessage(
                    "GeoGlyph", "Necesitas al menos 3 puntos para crear un polígono.", level=1)

    def keyPressEvent(self, event):
        # Cancela el dibujo apretando Esc
        if event.key() == Qt.Key_Escape:
            self._cancelar()

    def _finalizar_poligono(self):
        # Cierra el polígono y con el callback obtiene la geometría
        geometry = QgsGeometry.fromPolygonXY([self.points])
        self._limpiar()
        # llama a la función que guarda la anotación
        self.on_polygon_drawn(geometry)

    def _cancelar(self):
        # Esto para sacar el polígono que se está haciendo
        self._limpiar()

    def _limpiar(self):
        # Limpia los puntos
        self.points = []
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
