# Se encarga de guardar el polígono creado
# Para esto crea una capa annotations con todos los pologonos que dibuje el usuario
# Y adenás guarda el polígono en un archivo .gpkg en el computador.


import os
from datetime import datetime

from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
)
from qgis.PyQt.QtCore import QVariant


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

        # Estilo visual de polígono azul
        layer.renderer().symbol().setColor(
            __import__(
                'qgis.PyQt.QtGui',
                fromlist=['QColor']).QColor(
                0,
                120,
                255,
                80))

        QgsProject.instance().addMapLayer(layer)
        return layer

    def agregar_anotacion(self, geometry: QgsGeometry) -> QgsFeature:
        # Agrega una anotación con estado 'pending' a la capa

        feature = QgsFeature(self.layer.fields())
        feature.setGeometry(geometry)  # Es la geometría del polígono dibujado
        feature.setAttribute("status", "pending")
        feature.setAttribute("origin", "human")
        feature.setAttribute("timestamp", datetime.utcnow().isoformat())

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
