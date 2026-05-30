# TIGS 100: Split View Manager
# Maneja la vista dividida (split view) que permite comparar dos configuraciones
# de realce visual al mismo tiempo dentro de QGIS.

# Se decidió hacer la vista secundaria como un panel acoplable (QDockWidget)
# Un QDockWidget es el mismo tipo de panel que usa el panel lateral del de GeoGlyph.
# Este permite al usuario: Acoplarlo a cualquier lado de la ventana, flotarlo como ventana independiente,
# minimizarlo sin cerrarlo y ponerlo lado a lado con el mapa principal

# -*- coding: utf-8 -*-

from qgis.core import QgsProject
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDockWidget, QLabel, QSizePolicy, QVBoxLayout, QWidget


# Crea y gestiona el panel acoplable con el segundo canvas para la vista dividida.
class SplitViewManager:
    # Necesito de geoglyph.py:
    # self._split_view = SplitViewManager(self.iface)
    # self._split_view.activar()                         muestra el panel acoplable
    # self._split_view.desactivar()                      lo cierra y limpia

    # Inicializa el manager sin crear el segundo canvas,
    def __init__(self, iface):
        self.iface = iface
        self._canvas_secundario = None  # El segundo canvas vive dentro de un panel acoplable (QDockWidget).
        self._dock = None  # El panel acoplable
        self._sincronizado = True  # Aviso de sincronización: ON por defecto.
        self._activo = False  # Aviso que indica si el split view está visible actualmente.

        # Callback opcional para notificar a geoglyph.py cuando el usuario cierra el panel con la X.
        self._on_ventana_cerrada_callback = None

    # Lógica para activar la split view
    def activar(self):

        if self._activo:  # Si ya está activo, solo traer el panel al frente.
            if self._dock is not None:
                self._dock.raise_()
            return

        canvas_principal = self.iface.mapCanvas()

        # Crear el panel acoplable.
        # QDockWidget es el mismo tipo de widget que usa el panel de GeoGlyph.
        self._dock = QDockWidget("GeoGlyph — Vista Secundaria", self.iface.mainWindow())
        self._dock.setObjectName("GeoGlyphDockSecundario")

        # Permitir que el usuario acople el panel en cualquier lado.
        self._dock.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea
        )

        # Cuando el usuario cierra el panel con la X, avisar a geoglyph.py para que actualice el estado del botón
        self._dock.visibilityChanged.connect(self._on_visibilidad_cambiada)

        # Crear el contenido del panel (canvas)
        contenido = QWidget()
        layout = QVBoxLayout(contenido)
        layout.setContentsMargins(0, 0, 0, 0)

        # Etiqueta informativa en la parte superior del panel.
        lbl = QLabel("Vista Secundaria")
        lbl.setStyleSheet("color: gray; font-size: 10px; padding: 4px;")
        layout.addWidget(lbl)

        # Crear el segundo canvas.
        self._canvas_secundario = QgsMapCanvas()
        self._canvas_secundario.setObjectName("GeoGlyphCanvasSecundario")
        self._canvas_secundario.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Configurar el mismo CRS que el canvas principal para que las coordenadas coincidan entre ambas vistas.
        self._canvas_secundario.setDestinationCrs(canvas_principal.mapSettings().destinationCrs())
        layout.addWidget(self._canvas_secundario)
        self._dock.setWidget(contenido)

        # Cargar las mismas capas del proyecto.
        self._sincronizar_capas()

        # Copiar el extent actual del canvas principal.
        self._canvas_secundario.setExtent(canvas_principal.extent())
        self._canvas_secundario.refresh()

        # Conectar sincronización si está habilitada.
        if self._sincronizado:
            self._conectar_sincronizacion()

        # Agregar el canvas a QGIS en la parte inferior por defecto.
        self.iface.mainWindow().addDockWidget(Qt.BottomDockWidgetArea, self._dock)
        self._dock.show()
        self._activo = True

    # Lógica para desactivar la split view
    def desactivar(self):

        if not self._activo:
            return

        self._desconectar_sincronizacion()

        if self._dock is not None:
            # Desconectar la señal antes de cerrar para no entrar en loop.
            try:
                self._dock.visibilityChanged.disconnect(self._on_visibilidad_cambiada)
            except Exception:
                pass
            # Quitar el panel de la ventana principal de QGIS.
            self.iface.mainWindow().removeDockWidget(self._dock)
            self._dock.deleteLater()
            self._dock = None

        self._canvas_secundario = None
        self._activo = False

    # Callback para detectar cuando el usuario cierra el panel con la X.
    def _on_visibilidad_cambiada(self, visible):
        if not visible and self._activo:
            # El usuario cerró el panel con la X.
            self._canvas_secundario = None
            self._activo = False

            self._desconectar_sincronizacion()

            # Notificar a geoglyph.py para que actualice el botón.
            if self._on_ventana_cerrada_callback is not None:
                self._on_ventana_cerrada_callback()

    # Retorna True si el split view está visible actualmente.
    def esta_activo(self):
        return self._activo

    # Sincronización de zoom y pan

    # Activa o desactiva la sincronización de zoom y pan.
    def set_sincronizacion(self, activar: bool):
        self._sincronizado = activar

        if not self._activo:
            return

        if activar:
            self._conectar_sincronizacion()
        else:
            self._desconectar_sincronizacion()

    # Conecta extentsChanged del canvas principal al callback. Este se emite cada vez que el usuario
    # hace zoom o pan, lo que replica esos cambios en el canvas secundario.
    def _conectar_sincronizacion(self):

        canvas_principal = self.iface.mapCanvas()
        try:
            canvas_principal.extentsChanged.connect(self._on_extent_changed)
        except Exception:
            pass

    # Desconecta la señal de sincronización
    def _desconectar_sincronizacion(self):
        canvas_principal = self.iface.mapCanvas()
        try:
            canvas_principal.extentsChanged.disconnect(self._on_extent_changed)
        except Exception:
            pass

    # Copia el extent del canvas principal al secundario.
    def _on_extent_changed(self):
        if self._canvas_secundario is None:
            return

        canvas_principal = self.iface.mapCanvas()
        self._canvas_secundario.blockSignals(True)  # Bloquea la señar para que no haya un loop infinito de señales.
        self._canvas_secundario.setExtent(canvas_principal.extent())
        self._canvas_secundario.refresh()
        self._canvas_secundario.blockSignals(False)  # Desbloquea la señal.

    # Capas del canvas secundario
    # Carga en el canvas secundario las mismas capas del proyecto.
    def _sincronizar_capas(self):
        if self._canvas_secundario is None:
            return

        root = QgsProject.instance().layerTreeRoot()
        capas = [node.layer() for node in root.findLayers() if node.layer() is not None]
        self._canvas_secundario.setLayers(capas)

    # Retorna el canvas secundario, o None si no está activo.
    def get_canvas_secundario(self):
        return self._canvas_secundario
