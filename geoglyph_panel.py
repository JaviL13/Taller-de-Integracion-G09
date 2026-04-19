
#Se importan los componentes visuales
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout,
    QPushButton, QLabel, QFrame
)
#Q DockWidget es el panel lateral
#Q Widget es para el contenedor vacío primero
#QVBocLayout apila verticalmente los elementos
#QPush Button es para los botones
#QLabel es para ponerle etiquetas
#QFrame sirve como linea separadora

from qgis.PyQt.QtCore import Qt #Estas son las constantes de Qt como AlignTop o RightDockWidgetArea
from qgis.PyQt.QtGui import QIcon #Para iconos pero finalmente no se usó


class GeoGlyphPanel(QDockWidget): #Se crea geoglyph que hereda de QDockWidget
    #Panel lateral de GeoGlyph

    def __init__(self, iface, parent=None): #Recibe iface (interfaz de QGIS)
        super(GeoGlyphPanel, self).__init__("GeoGlyph", parent) #ventana principal de QGIS von titulo GeoGlyph
        self.iface = iface
        self.setObjectName("GeoGlyphPanel")  
        #Le da un nombre único al panel. QGIS usa este nombre para recordar la posición del panel entre sesiones (si se mueve a la izquierda, la próxima vez aparece en la izquierda)

        # Widget contenedor principal
        #No se pueden poner botones por separado, por eso un widget contenedor
        container = QWidget() 
        layout = QVBoxLayout() 
        layout.setAlignment(Qt.AlignTop)
        container.setLayout(layout) #Se crea un contenedor y los botones se alinean verticalmente

        #Cargar GeoTIFF 
        layout.addWidget(self._seccion_titulo("Cargar imagen"))

        self.btn_abrir_tiff = QPushButton("Abrir GeoTIFF") #Crea botón para abrir el archivo
        self.btn_abrir_tiff.setToolTip("Abre un archivo GeoTIFF")
        layout.addWidget(self.btn_abrir_tiff)

        layout.addWidget(self._separador()) #Linea para separar enre secciones

        #Realce Visual
        layout.addWidget(self._seccion_titulo(" Realce visual")) #Igual a la sección anterior pero  para la parte de realce visual.

        #Todos estos son botones a aconectarse más adelante
        btn_color_ramp = QPushButton("Aplicar Color Ramp")
        btn_color_ramp.setToolTip("Aplica una rampa de color para realce arqueológico")
        btn_color_ramp.setEnabled(False) #Por eso dicen setEnabled(False), no se encuentran conectados
        layout.addWidget(btn_color_ramp)

        btn_decorrelation = QPushButton("Decorrelation Stretch")
        btn_decorrelation.setToolTip("Realce por decorrelación espectral")
        btn_decorrelation.setEnabled(False)
        layout.addWidget(btn_decorrelation)

        btn_side_by_side = QPushButton("Vista Side-by-Side")
        btn_side_by_side.setToolTip("Compara dos configuraciones de visualización en paralelo")
        btn_side_by_side.setEnabled(False)
        layout.addWidget(btn_side_by_side)

        layout.addWidget(self._separador())

        #Anotaciones 
        layout.addWidget(self._seccion_titulo(" Anotaciones"))

        btn_importar = QPushButton("Importar detecciones")
        btn_importar.setToolTip("Importa detecciones en formato GeoJSON o probability map TIFF")
        btn_importar.setEnabled(False)
        layout.addWidget(btn_importar)

        btn_exportar = QPushButton("Exportar anotaciones")
        btn_exportar.setToolTip("Exporta las anotaciones validadas como GeoJSON")
        btn_exportar.setEnabled(False)
        layout.addWidget(btn_exportar)

        layout.addWidget(self._separador())

        # Sección: Inferencia ML 
        layout.addWidget(self._seccion_titulo(" Inferencia ML"))

        btn_inferencia = QPushButton("Ejecutar inferencia SAM")
        btn_inferencia.setToolTip("Ejecuta el modelo SAM sobre la región seleccionada")
        btn_inferencia.setEnabled(False)
        layout.addWidget(btn_inferencia)

        # Espaciador al final para más orden
        layout.addStretch()

        self.setWidget(container) 

    def _seccion_titulo(self, texto):
        #Crea una etiqueta de título de sección, se usa más arriba
        label = QLabel(texto)
        label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        return label

    def _separador(self):
        #Crea una línea separadora horizontal, se usa más arriba
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line