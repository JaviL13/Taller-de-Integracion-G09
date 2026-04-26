# Se encarga de guardar el polígono creado
# Para esto crea una capa annotations con todos los pologonos que dibuje el usuario
# Y adenás guarda el polígono en un archivo .gpkg en el computador.
#
# TIGS-64: agrega ciclo de vida (aprobar / rechazar) y feedback visual
# vía renderer categorizado por estado.


import os
from datetime import datetime, timezone

from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsSymbol,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

from .annotation_state import (
    AnnotationState,
    color_for_state,
    validate_transition,
)


GPKG_TABLE = "annotations"


class AnnotationManager:
    # Crea y gestiona la capa de anotaciones y guarda cada anotación en un
    # GeoPackage local.

    def __init__(self, gpkg_path, crs):
        # Ruta a archivo .gpkg donde se guardan anotaciones del usuario
        self.gpkg_path = gpkg_path
        self.crs = crs  # Dice cómo interpretar las coordenadas de la imagen
        self.layer = self._get_or_create_layer()

    def _get_or_create_layer(self):
        # Busca la capa annotations en el proyecto y si no existe la crea y
        # registra en QGIS

        # Busca si ya existe en el proyecto
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == GPKG_TABLE:
                return layer

        # Crea capa en la memoria con los campos necesarios
        layer = QgsVectorLayer(
            f"Polygon?crs={self.crs.authid()}",
            GPKG_TABLE,
            "memory"
        )
        provider = layer.dataProvider()
        provider.addAttributes([  # Columnas de la tabla
            # pending, approved o rejected
            QgsField("status", QVariant.String),
            QgsField("origin", QVariant.String),   # humano o machine learning
            QgsField("timestamp", QVariant.String),   # fecha y hora
        ])
        layer.updateFields()

        # Estilo visual: renderer categorizado por estado.
        # Cada categoría usa el color que define annotation_state.color_for_state.
        QgsProject.instance().addMapLayer(layer)
        self._aplicar_estilo_por_estado(layer)
        return layer

    def agregar_anotacion(self, geometry: QgsGeometry) -> QgsFeature:
        # Agrega una anotación con estado 'pending' a la capa

        feature = QgsFeature(self.layer.fields())
        feature.setGeometry(geometry)  # Es la geometría del polígono dibujado
        feature.setAttribute("status", "pending")
        feature.setAttribute("origin", "human")
        feature.setAttribute(
            "timestamp", datetime.now(timezone.utc).isoformat()
        )

        self.layer.dataProvider().addFeature(feature)
        self.layer.updateExtents()
        self.layer.triggerRepaint()

        # Guardar en GeoPackage
        self._guardar_gpkg()

        return feature  # Entrega el Qgs Feature creado

    def _guardar_gpkg(self):
        # Exporta la capa completa al GeoPackage
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = GPKG_TABLE

        # Si el archivo ya existe, agrega o reemplaza la tabla
        if os.path.exists(self.gpkg_path):
            options.actionOnExistingFile = (
                QgsVectorFileWriter.CreateOrOverwriteLayer
            )

        QgsVectorFileWriter.writeAsVectorFormatV3(
            self.layer,
            self.gpkg_path,
            QgsCoordinateTransformContext(),
            options,
        )

    # ── TIGS-64: ciclo de vida (aprobar / rechazar) ────────────────────────

    def aprobar_anotacion(self, feature_id: int) -> bool:
        """Cambia el status del feature a 'approved' y persiste el cambio.

        Retorna True si la anotación fue actualizada. Lanza
        StateTransitionError si la transición no es válida (p.ej.
        intentar aprobar algo que ya está approved).
        """
        return self._cambiar_estado(feature_id, AnnotationState.APPROVED)

    def rechazar_anotacion(self, feature_id: int) -> bool:
        """Cambia el status del feature a 'rejected' y persiste el cambio.

        Retorna True si la anotación fue actualizada. Lanza
        StateTransitionError si la transición no es válida.
        """
        return self._cambiar_estado(feature_id, AnnotationState.REJECTED)

    def _cambiar_estado(self, feature_id: int, nuevo_estado: AnnotationState) -> bool:
        """Helper interno: valida la transición, actualiza atributos y persiste.

        El método público (aprobar / rechazar) decide el estado destino;
        este método se encarga de la lógica genérica que aplica a cualquier
        cambio de estado.
        """
        feature = self.layer.getFeature(feature_id)
        if not feature.isValid():
            return False

        # Lee el estado actual y valida la transición. Si no es válida,
        # el módulo annotation_state lanza StateTransitionError; lo dejamos
        # propagar para que el llamante decida qué hacer.
        estado_actual = feature.attribute("status")
        validate_transition(estado_actual, nuevo_estado)

        # Mapeo de nombre de campo a índice (la API de QGIS quiere índices).
        idx_status = self.layer.fields().indexFromName("status")
        idx_timestamp = self.layer.fields().indexFromName("timestamp")
        nuevo_ts = datetime.now(timezone.utc).isoformat()

        ok = self.layer.dataProvider().changeAttributeValues({
            feature_id: {
                idx_status: nuevo_estado.value,
                idx_timestamp: nuevo_ts,
            }
        })
        if not ok:
            return False

        # Persistir en disco y refrescar la visualización.
        self._guardar_gpkg()
        self.layer.triggerRepaint()
        return True

    def aplicar_estilo_por_estado(self):
        """API pública para refrescar el estilo categorizado.

        Se puede llamar desde fuera (p.ej. desde el panel) para forzar un
        repintado tras cambios masivos.
        """
        self._aplicar_estilo_por_estado(self.layer)

    def _aplicar_estilo_por_estado(self, layer):
        """Configura el renderer categorizado de la capa por el campo 'status'.

        Crea una categoría por cada estado de AnnotationState con el color
        definido en annotation_state.color_for_state. Es idempotente: se
        puede llamar varias veces sin duplicar categorías (cada llamada
        reemplaza al renderer anterior).
        """
        categorias = []
        for estado in AnnotationState:
            r, g, b, a = color_for_state(estado)
            simbolo = QgsSymbol.defaultSymbol(QgsWkbTypes.PolygonGeometry)
            simbolo.setColor(QColor(r, g, b, a))
            categorias.append(
                QgsRendererCategory(estado.value, simbolo, estado.value)
            )

        renderer = QgsCategorizedSymbolRenderer("status", categorias)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
