# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


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
        # Aplicar sobre: vista actual o imagen completa
        color_layout.addWidget(QLabel("Aplicar sobre:"))
        self.combo_color_ramp_extent = QComboBox()
        self.combo_color_ramp_extent.addItems(
            [
                "Vista actual",
                "Imagen completa",
            ]
        )
        color_layout.addWidget(self.combo_color_ramp_extent)
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

        self.btn_side_by_side = QPushButton("Activar vista Side-by-Side")
        self.btn_side_by_side.setToolTip("Compara dos configuraciones de visualización en paralelo")
        self.btn_side_by_side.setEnabled(True)
        layout.addWidget(self.btn_side_by_side)

        # TIGS 100: botón para activar/desactivar la sincronización
        self.btn_sync = QPushButton("Sincronización: ON")
        self.btn_sync.setToolTip("Activa o desactiva la sincronización de zoom y pan entre los 2 canvas")
        self.btn_sync.setEnabled(False)  # Se habilitar con el split view
        layout.addWidget(self.btn_sync)

        # Label de estado del realce (Color Ramp / DStretch) — TIGS-S5-04
        self.lbl_enhance_status = QLabel("")
        self.lbl_enhance_status.setWordWrap(True)
        self.lbl_enhance_status.setStyleSheet("color: gray; font-size: 10px; margin-left: 4px;")
        layout.addWidget(self.lbl_enhance_status)

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

        # Importar anotaciones en GeoJson
        self.btn_importar_geojson = QPushButton("Importar anotaciones")
        self.btn_importar_geojson.setToolTip("Importa anotaciones en formato GeoJSON")
        layout.addWidget(self.btn_importar_geojson)

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

        # TIGS-87: Historial de notas con trazabilidad ──────────────────────
        # Tabla que muestra el historial completo de notas del polígono
        # seleccionado, ordenadas cronológicamente (más antigua arriba).
        layout.addWidget(QLabel("Historial de notas:"))
        self.table_historial_notas = QTableWidget()
        self.table_historial_notas.setColumnCount(5)
        self.table_historial_notas.setHorizontalHeaderLabels(["Fecha", "Nota", "Estado", "Origen", "Score"])
        self.table_historial_notas.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_historial_notas.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_historial_notas.setAlternatingRowColors(True)
        self.table_historial_notas.horizontalHeader().setStretchLastSection(True)
        self.table_historial_notas.setMaximumHeight(130)
        self.table_historial_notas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.table_historial_notas)

        # Campo para agregar una nota nueva (no sobreescribe las anteriores)
        self.input_notas = QLineEdit()
        self.input_notas.setPlaceholderText("Agregar nota ...")
        layout.addWidget(self.input_notas)
        self.btn_agregar_nota = QPushButton("Agregar nota")
        self.btn_agregar_nota.setToolTip(
            "Guarda la nota en el historial del polígono seleccionado (no elimina notas anteriores)"
        )
        self.btn_agregar_nota.setEnabled(False)
        layout.addWidget(self.btn_agregar_nota)

        self.btn_aprobar = QPushButton("Aprobar")
        self.btn_aprobar.setToolTip("Marca la anotación seleccionada como aprobada (verde)")
        self.btn_aprobar.setEnabled(False)
        layout.addWidget(self.btn_aprobar)

        self.btn_rechazar = QPushButton("Rechazar")
        self.btn_rechazar.setToolTip("Marca la anotación seleccionada como rechazada (rojo)")
        self.btn_rechazar.setEnabled(False)
        layout.addWidget(self.btn_rechazar)

        self.btn_pendiente = QPushButton("Pendiente")
        self.btn_pendiente.setToolTip("Devuelve la anotación seleccionada al estado pendiente (naranja)")
        self.btn_pendiente.setEnabled(False)
        layout.addWidget(self.btn_pendiente)

        layout.addWidget(self._separador())

        # Inferencia ML
        layout.addWidget(self._seccion_titulo(" Inferencia ML"))

        self.btn_ejecutar_sam = QPushButton("Ejecutar SAM")
        self.btn_ejecutar_sam.setToolTip("Ejecuta el modelo SAM sobre el ROI activo. Selecciona un ROI primero.")
        self.btn_ejecutar_sam.setEnabled(False)
        layout.addWidget(self.btn_ejecutar_sam)

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

        # Banner de estado del backend — visible solo cuando está caído
        self.lbl_backend_status = QLabel("⚠ Backend no disponible")
        self.lbl_backend_status.setAlignment(Qt.AlignCenter)
        self.lbl_backend_status.setStyleSheet(
            "background-color: #c0392b; color: white; font-weight: bold; padding: 4px; font-size: 11px;"
        )
        self.lbl_backend_status.setVisible(False)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout()
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.addWidget(self.lbl_backend_status)
        wrapper_layout.addWidget(self.tabs)
        wrapper.setLayout(wrapper_layout)
        self.setWidget(wrapper)

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
