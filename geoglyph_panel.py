# -*- coding: utf-8 -*-
# import os
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout,
    QPushButton, QLabel, QFrame, QComboBox,
    QLineEdit
)
from qgis.PyQt.QtCore import Qt


class GeoGlyphPanel(QDockWidget):
    # Panel lateral acoplable de GeoGlyph

    def __init__(self, iface, parent=None):
        super(GeoGlyphPanel, self).__init__("GeoGlyph", parent)
        self.iface = iface
        self.setObjectName("GeoGlyphPanel")
        # Le da un nombre único al panel. QGIS usa este nombre para recordar la
        # posición del panel entre sesiones (si se mueve a la izquierda, la
        # próxima vez aparece en la izquierda)

        # Widget contenedor principal
        # No se pueden poner botones por separado, por eso un widget contenedor
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

        # Integración realce, que permita seleccionar color ramp o dStretch
        layout.addWidget(QLabel("Tipo de realce:"))
        self.combo_enhance = QComboBox()
        self.combo_enhance.addItems(["Color Ramp", "Decorrelation Stretch"])
        layout.addWidget(self.combo_enhance)
        self.combo_enhance.currentTextChanged.connect(self.toggle_ui)

        self.btn_apply = QPushButton("Aplicar Realce")
        self.btn_apply.setToolTip("Aplica el método de realce seleccionado")
        layout.addWidget(self.btn_apply)

        # Color Ramp (Opciones si se escoge este realce)
        self.color_ramp_container = QWidget()
        color_layout = QVBoxLayout()
        # Escoger banda
        color_layout.addWidget(QLabel("Banda:"))
        self.combo_band = QComboBox()
        color_layout.addWidget(self.combo_band)
        # Opciones esquemas de colores
        color_layout.addWidget(QLabel("Esquema de color:"))
        self.combo_color_ramp = QComboBox()
        self.combo_color_ramp.addItems(["viridis", "RdYlGn"])
        color_layout.addWidget(self.combo_color_ramp)
        # Estiramiento de contraste
        color_layout.addWidget(QLabel("Estiramiento de contraste (Min/Max)"))
        self.input_min = QLineEdit()
        self.input_min.setPlaceholderText("Auto")
        color_layout.addWidget(self.input_min)
        self.input_max = QLineEdit()
        self.input_max.setPlaceholderText("Auto")
        color_layout.addWidget(self.input_max)
        self.color_ramp_container.setLayout(color_layout)
        layout.addWidget(self.color_ramp_container)
        self.toggle_ui()

        btn_side_by_side = QPushButton("Vista Side-by-Side")
        btn_side_by_side.setToolTip(
            "Compara dos configuraciones de visualización en paralelo (próximamente)")
        btn_side_by_side.setEnabled(False)
        layout.addWidget(btn_side_by_side)

        layout.addWidget(self._separador())

        # Anotaciones
        layout.addWidget(self._seccion_titulo(" Anotaciones"))

        # Botón para dibujar el polígono
        self.btn_dibujar = QPushButton("Dibujar polígono")
        self.btn_dibujar.setToolTip(
            "Activa la herramienta de dibujo: "
            "clic izquierdo agrega vértices, "
            "clic derecho cierra el polígono"
        )
        layout.addWidget(self.btn_dibujar)

        # TIGS-53: botón para seleccionar un ROI rectangular y enviarlo al
        # backend (POST /infer). Se ubica junto a "Dibujar polígono" porque
        # ambos botones activan herramientas de selección sobre el canvas.
        self.btn_roi = QPushButton("Seleccionar ROI (rect)")
        self.btn_roi.setToolTip(
            "Activa la herramienta de selección rectangular: "
            "arrastra para definir un ROI y enviar a /infer en el backend"
        )
        layout.addWidget(self.btn_roi)

        btn_importar = QPushButton("Importar detecciones")
        btn_importar.setToolTip(
            "Importa detecciones en formato GeoJSON o probability map TIFF (próximamente)")
        btn_importar.setEnabled(False)
        layout.addWidget(btn_importar)

        # Exportar la capa realzada como GeoTIFF
        self.btn_exportar = QPushButton("Exportar Capa Realzada")
        # Tooltip que explica qué hace el botón
        self.btn_exportar.setToolTip(
            "Guarda la capa realzada activa como archivo GeoTIFF")
        # Habilitado para hacerle clic
        self.btn_exportar.setEnabled(True)
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
        self.lbl_status.setStyleSheet(
            "color: gray; font-size: 10px; margin-left: 4px;")
        layout.addWidget(self.lbl_status)

        # Espaciador al final para más orden
        layout.addStretch()
        self.setWidget(container)

    def _seccion_titulo(self, texto):
        # Crea una etiqueta de título de sección.
        label = QLabel(texto)
        label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        return label

    def _separador(self):
        # Crea una línea separadora horizontal
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    # Muestre u oculte opciones de color ramp
    def toggle_ui(self):
        method = self.combo_enhance.currentText()

        if method == "Color Ramp":
            self.color_ramp_container.setVisible(True)
        else:
            self.color_ramp_container.setVisible(False)
