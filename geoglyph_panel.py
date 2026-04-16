# -*- coding: utf-8 -*-
import os
#Se importan los componentes visuales
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout,
    QPushButton, QLabel, QFrame, QSizePolicy, QComboBox,
    QLineEdit
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon


class GeoGlyphPanel(QDockWidget):
    """Panel lateral acoplable de GeoGlyph."""

    def __init__(self, iface, parent=None): #Recibe iface (interfaz de QGIS)
        super(GeoGlyphPanel, self).__init__("GeoGlyph", parent) #ventana principal de QGIS
        self.iface = iface
        self.setObjectName("GeoGlyphPanel")  # necesario para persistir entre sesiones
        #Le da un nombre único al panel. QGIS usa este nombre para recordar la posición del panel entre sesiones (si lo moviste a la izquierda, la próxima vez aparece en la izquierda). Sin esto, el panel no persiste.

        # Widget contenedor principal
        container = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        container.setLayout(layout)

        #Sección: Cargar GeoTIFF 
        layout.addWidget(self._seccion_titulo(" Cargar imagen"))

        self.btn_abrir_tiff = QPushButton("Abrir GeoTIFF")
        self.btn_abrir_tiff.setToolTip("Abre un archivo GeoTIFF y lo agrega como capa raster en QGIS")
        layout.addWidget(self.btn_abrir_tiff)

        layout.addWidget(self._separador())

        #  Sección: Realce Visual
        layout.addWidget(self._seccion_titulo(" Realce visual"))

        #Color Ramp
        self.btn_color_ramp = QPushButton("Aplicar Color Ramp")
        self.btn_color_ramp.setToolTip("Aplica una rampa de color para realce arqueológico")
        self.btn_color_ramp.setEnabled(True)
        layout.addWidget(self.btn_color_ramp)
        #Escoger banda
        layout.addWidget(QLabel("Banda:"))
        self.combo_band = QComboBox()
        layout.addWidget(self.combo_band)
        #Opciones esquemas de colores
        layout.addWidget(QLabel("Esquema de color:"))
        self.combo_color_ramp = QComboBox()
        self.combo_color_ramp.addItems(["viridis", "RdYlGn"])
        layout.addWidget(self.combo_color_ramp)
        #Estiramiento de contraste
        layout.addWidget(self._seccion_titulo(" Estiramiento de contraste (Min/Max)"))
        self.input_min = QLineEdit()
        self.input_min.setPlaceholderText("Auto")
        layout.addWidget(self.input_min)
        self.input_max = QLineEdit()
        self.input_max.setPlaceholderText("Auto")
        layout.addWidget(self.input_max)

        btn_decorrelation = QPushButton("Decorrelation Stretch")
        btn_decorrelation.setToolTip("Realce por decorrelación espectral (próximamente)")
        btn_decorrelation.setEnabled(False)
        layout.addWidget(btn_decorrelation)

        btn_side_by_side = QPushButton("Vista Side-by-Side")
        btn_side_by_side.setToolTip("Compara dos configuraciones de visualización en paralelo (próximamente)")
        btn_side_by_side.setEnabled(False)
        layout.addWidget(btn_side_by_side)

        layout.addWidget(self._separador())

        # Sección: Anotaciones 
        layout.addWidget(self._seccion_titulo(" Anotaciones"))

        btn_importar = QPushButton("Importar detecciones")
        btn_importar.setToolTip("Importa detecciones en formato GeoJSON o probability map TIFF (próximamente)")
        btn_importar.setEnabled(False)
        layout.addWidget(btn_importar)

        btn_exportar = QPushButton("Exportar anotaciones")
        btn_exportar.setToolTip("Exporta las anotaciones validadas como GeoJSON (próximamente)")
        btn_exportar.setEnabled(False)
        layout.addWidget(btn_exportar)

        layout.addWidget(self._separador())

        # Sección: Inferencia ML 
        layout.addWidget(self._seccion_titulo(" Inferencia ML"))

        btn_inferencia = QPushButton("Ejecutar inferencia SAM")
        btn_inferencia.setToolTip("Ejecuta el modelo SAM sobre la región seleccionada (próximamente)")
        btn_inferencia.setEnabled(False)
        layout.addWidget(btn_inferencia)

        # Espaciador al final
        layout.addStretch()

        self.setWidget(container)

    def _seccion_titulo(self, texto):
        """Crea una etiqueta de título de sección."""
        label = QLabel(texto)
        label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        return label

    def _separador(self):
        """Crea una línea separadora horizontal."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line