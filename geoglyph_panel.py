# -*- coding: utf-8 -*-
# import os
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QComboBox, QDockWidget, QFrame, QHBoxLayout, QLabel, QLineEdit, 
QPushButton, QScrollArea, QTabWidget, QTableWidget QVBoxLayout, QWidget)

class GeoGlyphPanel(QDockWidget):
    # Panel lateral acoplable de GeoGlyph

    def __init__(self, iface, parent=None):
        super(GeoGlyphPanel, self).__init__("GeoGlyph", parent)
        self.iface = iface
        self.setObjectName("GeoGlyphPanel")
        
        # Esto es para hacer las pestañas
        self.tabs = QTabWidget()
        
        # TAB 1 - Panel Actual
        tab_main = QWidget()
        tab_main_layout = QVBoxLayout()
        tab_main.setLayout(tab_main_layout)
    
        scroll = QScrollArea()  # Agregué un scroll para que se vea el panel completo
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        container.setLayout(layout)
        scroll.setWidget(container)

        tab_main_layout.addWidget(scroll)
        self.tabs.addTab(tab_main, "Principal")

        # Cargar GeoTIFF
        layout.addWidget(self._seccion_titulo(" Cargar imagen"))

        self.btn_abrir_tiff = QPushButton("Abrir GeoTIFF")
        self.btn_abrir_tiff.setToolTip("Abre un archivo GeoTIFF y lo agrega como capa raster en QGIS")
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
        btn_side_by_side.setToolTip("Compara dos configuraciones de visualización en paralelo (próximamente)")
        btn_side_by_side.setEnabled(False)
        layout.addWidget(btn_side_by_side)

        layout.addWidget(self._separador())

        # Anotaciones
        layout.addWidget(self._seccion_titulo(" Anotaciones"))

        # Botón para dibujar el polígono
        self.btn_dibujar = QPushButton("Dibujar polígono")
        self.btn_dibujar.setToolTip(
            "Activa la herramienta de dibujo: clic izquierdo agrega vértices, clic derecho cierra el polígono"
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
        btn_importar.setToolTip("Importa detecciones en formato GeoJSON o probability map TIFF (próximamente)")
        btn_importar.setEnabled(False)
        layout.addWidget(btn_importar)

        # Exportar anotaciones aprobadas en GeoJson
        self.btn_exportar_geojson = QPushButton("Exportar anotaciones")
        self.btn_exportar_geojson.setToolTip("Exporta las anotaciones aprobadas en formato GeoJSON")
        layout.addWidget(self.btn_exportar_geojson)

        # Exportar la capa realzada como GeoTIFF
        self.btn_exportar = QPushButton("Exportar Capa Realzada")
        # Tooltip que explica qué hace el botón
        self.btn_exportar.setToolTip("Guarda la capa realzada activa como archivo GeoTIFF")
        # Habilitado para hacerle clic
        self.btn_exportar.setEnabled(True)
        layout.addWidget(self.btn_exportar)

        layout.addWidget(self._separador())

        # Estado de anotación (TIGS-64)
        # Sección que permite aprobar o rechazar la anotación seleccionada
        # en el mapa. Los botones quedan deshabilitados hasta que el usuario
        # selecciona al menos un feature en la capa annotations (la
        # habilitación la maneja geoglyph.py vía la señal selectionChanged).
        layout.addWidget(self._seccion_titulo(" Estado de anotación"))

        # Label que muestra cuántas anotaciones hay seleccionadas. Sirve de
        # feedback inmediato para que el usuario sepa por qué los botones
        # están deshabilitados (porque no hay nada seleccionado).
        self.lbl_seleccion = QLabel("Selección actual: 0 anotaciones")
        self.lbl_seleccion.setStyleSheet("color: gray; font-size: 10px; margin-left: 4px;")
        layout.addWidget(self.lbl_seleccion)

        # Label para mostrar el score de confianza de la detección
        # El valor se actualiza desde geoglyph.py con el resultado del backend
        self.lbl_confianza = QLabel("Confianza: —")
        self.lbl_confianza.setStyleSheet("color: gray; font-size: 10px; margin-left: 4px;")
        layout.addWidget(self.lbl_confianza)

        # Campo de texto libre para observaciones
        self.input_notas = QLineEdit()
        self.input_notas.setPlaceholderText("Notas ...")
        layout.addWidget(self.input_notas)

        self.btn_aprobar = QPushButton("Aprobar")
        self.btn_aprobar.setToolTip("Marca la anotación seleccionada como aprobada (verde)")
        self.btn_aprobar.setEnabled(False)
        layout.addWidget(self.btn_aprobar)

        self.btn_rechazar = QPushButton("Rechazar")
        self.btn_rechazar.setToolTip("Marca la anotación seleccionada como rechazada (rojo)")
        self.btn_rechazar.setEnabled(False)
        layout.addWidget(self.btn_rechazar)

        layout.addWidget(self._separador())

        # Inferencia ML
        layout.addWidget(self._seccion_titulo(" Inferencia ML"))

        self.btn_inferencia = QPushButton("Ejecutar inferencia SAM")
        self.btn_inferencia.setToolTip(
            "Temporalmente deshabilitado: la inferencia SAM se ejecuta automáticamente al seleccionar ROI"
        )
        self.btn_inferencia.setEnabled(False)
        layout.addWidget(self.btn_inferencia)

        # Boton para renderizar
        self.btn_infer = QPushButton("Renderizar segmentación")
        self.btn_infer.setToolTip("Llama a POST /infer y renderiza los polígonos resultantes como capa vectorial")
        self.btn_infer.setEnabled(True)
        layout.addWidget(self.btn_infer)

        # Label de estado de la última llamada HTTP
        self.lbl_status = QLabel("Estado: —")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: gray; font-size: 10px; margin-left: 4px;")
        layout.addWidget(self.lbl_status)

        # Label de score de confianza que devuelve el backend después de la inferencia
        self.lbl_score = QLabel("Confianza: —")
        self.lbl_score.setWordWrap(True)
        self.lbl_score.setStyleSheet("color: gray; font-size: 10px; margin-left: 4px;")
        layout.addWidget(self.lbl_score)

        # Espaciador al final para más orden
        layout.addStretch()

        # TAB 2 - Listado de polígonos 
        tab_poligonos = QWidget()
        poligonos_layout = QVBoxLayout()
        tab_poligonos.setLayout(poligonos_layout)

        # Filtro por estados
        filtro_layout = QHBoxLayout()
        filtro_layout.addWidget(QLabel("Filtrar por estado:"))
        self.combo_filtro_estado = QComboBox()
        self.combo_filtro_estado.addItems(["All", "Approved", "Rejected", "Pending"])
        filtro_layout.addWidget(self.combo_filtro_estado)
        poligonos_layout.addLayout(filtro_layout)

        # Tabla de polígonos
        self.table_poligonos = QTableWidget()
        self.table_poligonos.setColumnCount(3)
        self.table_poligonos.setHorizontalHeaderLabels(["Estado", "Origen", "Score"])
        poligonos_layout.addWidget(self.table_poligonos)
        self.tabs.addTab(tab_poligonos, "Polígonos")

        self.setWidget(self.tabs)

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
