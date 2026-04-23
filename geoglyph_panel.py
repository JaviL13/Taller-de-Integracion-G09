# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout,
    QPushButton, QLabel, QFrame, QSizePolicy, QComboBox,
    QLineEdit
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon


class GeoGlyphPanel(QDockWidget):
    #Panel lateral acoplable de GeoGlyph

    def __init__(self, iface, parent=None):
        super(GeoGlyphPanel, self).__init__("GeoGlyph", parent)
        self.iface = iface
        self.setObjectName("GeoGlyphPanel")
        #Le da un nombre único al panel. QGIS usa este nombre para recordar la posición del panel entre sesiones (si se mueve a la izquierda, la próxima vez aparece en la izquierda)

        # Widget contenedor principal
        #No se pueden poner botones por separado, por eso un widget contenedor
        container = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        container.setLayout(layout)

        # Cargar GeoTIFF
        layout.addWidget(self._seccion_titulo(" Cargar imagen"))

        self.btn_abrir_tiff = QPushButton("Abrir GeoTIFF")
        self.btn_abrir_tiff.setToolTip(
            "Abre un archivo GeoTIFF y lo agrega como capa raster en QGIS"
        )
        layout.addWidget(self.btn_abrir_tiff)

        layout.addWidget(self._separador())

        # Realce Visual
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

        self.btn_decorrelation = QPushButton("Decorrelation Stretch")
        self.btn_decorrelation.setToolTip(
            "Aplica decorrelation stretch (PCA sobre 3 bandas) al raster seleccionado"
        )
        layout.addWidget(self.btn_decorrelation)

        btn_side_by_side = QPushButton("Vista Side-by-Side")
        btn_side_by_side.setToolTip("Compara dos configuraciones de visualización en paralelo (próximamente)")
        btn_side_by_side.setEnabled(False)
        layout.addWidget(btn_side_by_side)

        layout.addWidget(self._separador())

        # Anotaciones
        layout.addWidget(self._seccion_titulo(" Anotaciones"))

        #Botón para dibujar el polígono
        self.btn_dibujar = QPushButton("Dibujar polígono")
        self.btn_dibujar.setToolTip(
            "Activa la herramienta de dibujo: " \
            "clic izquierdo agrega vértices, "
            "clic derecho cierra el polígono"
        )
        layout.addWidget(self.btn_dibujar)

        btn_importar = QPushButton("Importar detecciones")
        btn_importar.setToolTip("Importa detecciones en formato GeoJSON o probability map TIFF (próximamente)")
        btn_importar.setEnabled(False)
        layout.addWidget(btn_importar)

        self.btn_exportar = QPushButton("Exportar Capa Realzada")                           # Exportar la capa realzada como GeoTIFF
        self.btn_exportar.setToolTip("Guarda la capa realzada activa como archivo GeoTIFF") # Tooltip que explica qué hace el botón
        self.btn_exportar.setEnabled(True)                                                  # Habilitado para hacerle clic
        layout.addWidget(self.btn_exportar)

        layout.addWidget(self._separador())

        # Inferencia ML
        layout.addWidget(self._seccion_titulo(" Inferencia ML"))

        self.btn_inferencia = QPushButton("Ejecutar inferencia SAM")
        self.btn_inferencia.setToolTip(
            "Envía la región seleccionada al backend FastAPI (POST /enhance)"
        )
        self.btn_inferencia.setEnabled(True)  # habilitado en TIGS-42
        layout.addWidget(self.btn_inferencia)

        # Label de estado de la última llamada HTTP
        self.lbl_status = QLabel("Estado: —")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: gray; font-size: 10px; margin-left: 4px;")
        layout.addWidget(self.lbl_status)

        # Espaciador al final para más orden
        layout.addStretch()
        self.setWidget(container)

    def _seccion_titulo(self, texto):
        #Crea una etiqueta de título de sección.
        label = QLabel(texto)
        label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        return label

    def _separador(self):
        #Crea una línea separadora horizontal
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line