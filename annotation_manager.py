# el contenido dentro del archivo se ha ocupado IA para poder aplicar técnicas más
# específicas y poder resolver errores de código que advertía la consola de qgis
# Se encarga de guardar el polígono creado.
# Crea una capa annotations respaldada por un archivo .gpkg en disco.
# Cada cambio (agregar polígono, aprobar/rechazar) se persiste automáticamente
# porque la capa usa el provider 'ogr' apuntando al GeoPackage.
#
# TIGS-64: agrega ciclo de vida (aprobar / rechazar) y feedback visual
# vía renderer categorizado por estado.
# TIGS-65: persistencia real al GeoPackage. La capa pasa de 'memory' a
# GPKG-backed (provider 'ogr') para que los cambios sobrevivan al cierre
# de QGIS y para no sobreescribir el archivo en cada guardado.

import json
import os
import sqlite3
from datetime import datetime, timezone

from qgis.core import (
    NULL,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRendererCategory,
    QgsSymbol,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

# Para exportar anotaciones como GeoJson
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QFileDialog

# Compatibilidad QGIS 3.38+: el constructor de QgsField con QVariant.Type
# quedó deprecado y prefiere QMetaType.Type. Hacemos fallback por si el
# plugin se ejecuta en una versión vieja de QGIS donde QMetaType no existe.
try:
    from qgis.PyQt.QtCore import QMetaType

    _FIELD_STRING = QMetaType.Type.QString
    _FIELD_DOUBLE = QMetaType.Type.Double
    _FIELD_INT = QMetaType.Type.Int
except (ImportError, AttributeError):
    _FIELD_STRING = QVariant.String
    _FIELD_DOUBLE = QVariant.Double
    _FIELD_INT = QVariant.Int


# Import relativo cuando se carga como parte del paquete del plugin (QGIS),
# absoluto como fallback cuando se importa suelto desde un test que solo
# añade el directorio del repo a sys.path.
try:
    from .annotation_state import (
        AnnotationState,
        color_for_state,
        validate_transition,
    )
except ImportError:
    from annotation_state import (
        AnnotationState,
        color_for_state,
        validate_transition,
    )


GPKG_TABLE = "annotations"

# Tabla de historial de notas (no espacial, gestionada vía sqlite3 directo).
GPKG_NOTES_TABLE = "annotation_notes"

# DDL de la tabla de notas. Se usa tanto para crearla en GPKGs nuevos como
# para migrar GPKGs existentes que no la tengan (CREATE TABLE IF NOT EXISTS).
_DDL_ANNOTATION_NOTES = """
CREATE TABLE IF NOT EXISTS annotation_notes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    annotation_id INTEGER NOT NULL,
    texto         TEXT    NOT NULL DEFAULT '',
    origen        TEXT    NOT NULL,
    estado        TEXT    NOT NULL,
    score         REAL,
    timestamp     TEXT    NOT NULL
);
"""

_DDL_ANNOTATION_NOTES_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_annotation_notes_annotation_id ON annotation_notes(annotation_id);"
)


class AnnotationManager:
    # Crea y gestiona la capa de anotaciones, respaldada por un GeoPackage
    # local. Cualquier cambio sobre la capa se persiste automáticamente al
    # archivo .gpkg porque la capa usa el provider 'ogr'.

    def __init__(self, gpkg_path, crs):
        # Ruta al archivo .gpkg donde se guardan las anotaciones del usuario.
        self.gpkg_path = gpkg_path
        # CRS con el que interpretar las coordenadas de la imagen.
        self.crs = crs
        # Capa GPKG-backed (puede ser nueva o cargada de un archivo existente).
        self.layer = self._get_or_create_layer()

    # ── Inicialización de la capa ──────────────────────────────────────────

    def _get_or_create_layer(self):
        """Devuelve la capa 'annotations' GPKG-backed.

        Estrategia:
        1. Si la capa ya está cargada en el proyecto QGIS, la reutiliza.
        2. Si el archivo .gpkg ya existe en disco, lo abre con provider
           'ogr' (los cambios se escriben directo al archivo).
        3. Si no existe, crea el archivo con la tabla 'annotations' vacía
           y luego lo abre con provider 'ogr'.

        Esto hace que los polígonos y sus cambios de estado persistan
        entre sesiones de QGIS sin sobreescribir el archivo cada vez.
        """
        # 1. ¿Ya está cargada la capa GPKG-backed en el proyecto?
        # Importante: solo reutilizar si el provider es 'ogr'. Si es 'memory'
        # significa que la capa quedó del código antiguo (pre-TIGS-65) o de
        # un proyecto .qgz guardado antes del refactor. En ese caso:
        #   - Rescatamos los features que pudieran tener (no se han persistido
        #     todavía) para no perder el trabajo del usuario.
        #   - Eliminamos las capas obsoletas del proyecto.
        #   - Cargamos la versión GPKG-backed e insertamos los rescatados.
        capas_obsoletas = []
        features_a_migrar = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == GPKG_TABLE:
                if layer.providerType() == "ogr":
                    return layer
                # Rescatar features de la capa memory antes de descartarla.
                for feat in layer.getFeatures():
                    features_a_migrar.append(feat)
                capas_obsoletas.append(layer.id())
        for layer_id in capas_obsoletas:
            QgsProject.instance().removeMapLayer(layer_id)

        # 2. Si el archivo no existe, hay que crearlo (con la tabla vacía).
        if not os.path.exists(self.gpkg_path):
            self._crear_gpkg_vacio()

        # 3. Abrir el .gpkg como capa con provider 'ogr'. La sintaxis
        #    {ruta}|layername={tabla} le dice a OGR qué tabla del .gpkg
        #    levantar (un .gpkg puede tener varias capas).
        uri = f"{self.gpkg_path}|layername={GPKG_TABLE}"
        layer = QgsVectorLayer(uri, GPKG_TABLE, "ogr")
        if not layer.isValid():
            raise RuntimeError(f"No se pudo abrir la capa '{GPKG_TABLE}' en {self.gpkg_path}")

        # Migración: asegurar que annotation_notes exista en GPKGs creados
        # antes de esta versión del plugin (que no la tenían).
        self._asegurar_tabla_notas()

        # 4. Migrar al GPKG los features rescatados de capas memory obsoletas.
        if features_a_migrar:
            nuevos = []
            for feat_viejo in features_a_migrar:
                nuevo = QgsFeature(layer.fields())
                nuevo.setGeometry(feat_viejo.geometry())
                # Copiar los 3 atributos por nombre. Si la capa vieja no
                # tenía alguno, se rellena con default razonable.
                nuevo.setAttribute(
                    "status",
                    feat_viejo.attribute("status")
                    if "status" in feat_viejo.fields().names()
                    else AnnotationState.PENDING.value,
                )
                nuevo.setAttribute(
                    "origin",
                    feat_viejo.attribute("origin") if "origin" in feat_viejo.fields().names() else "human",
                )
                nuevo.setAttribute(
                    "timestamp",
                    feat_viejo.attribute("timestamp")
                    if "timestamp" in feat_viejo.fields().names()
                    else datetime.now(timezone.utc).isoformat(),
                )
                nuevos.append(nuevo)
            layer.dataProvider().addFeatures(nuevos)

        # Registrar en el proyecto QGIS y aplicar el estilo categorizado.
        # Pasamos addToLegend=False y luego insertLayer(0, ...) para forzar
        # que la capa de anotaciones quede ARRIBA del raster en el árbol de
        # capas; si la dejamos al final, los polígonos quedan tapados por
        # la imagen y se ven invisibles aunque existan en la tabla.
        proyecto = QgsProject.instance()
        proyecto.addMapLayer(layer, False)
        proyecto.layerTreeRoot().insertLayer(0, layer)

        # TIGS 65: Archivo QML de respaldo
        exito = self._aplicar_estilo_por_estado(layer)  # Este es el estido definido en el código
        qml_path = os.path.join(os.path.dirname(__file__), "annotations_style.qml")  # Este es el QML de respaldo

        if exito:  # Si el estilo del código se aplica bien
            layer.triggerRepaint()  # Lo usa
        else:  # Si no se aplica, carga el QML de respaldo
            if os.path.exists(qml_path):
                mensaje, exito_qml = layer.loadNamedStyle(qml_path)
                if exito_qml:
                    layer.triggerRepaint()
        return layer

    def _crear_gpkg_vacio(self):
        """Crea el archivo .gpkg con la tabla 'annotations' vacía.

        Se usa una capa temporal en memoria solo como 'molde' para definir
        el esquema (campos y tipo de geometría), y luego se vuelca al .gpkg
        con QgsVectorFileWriter. Después de esta función, el archivo .gpkg
        existe en disco con la tabla creada pero sin features.
        """
        # Capa molde en memoria con los campos del esquema.
        molde = QgsVectorLayer(
            f"Polygon?crs={self.crs.authid()}",
            GPKG_TABLE,
            "memory",
        )
        provider = molde.dataProvider()
        provider.addAttributes(
            [
                # pending, approved o rejected
                QgsField("status", _FIELD_STRING),
                # 'human' (dibujado por el usuario) o 'ml' (importado del modelo)
                QgsField("origin", _FIELD_STRING),
                # Fecha y hora del último cambio (ISO 8601 UTC).
                QgsField("timestamp", _FIELD_STRING),
                # Score de confianza (solo aplica para origin='ml'; humano = NULL).
                QgsField("score", _FIELD_DOUBLE),
                # Notas del arqueólogo asociadas a este polígono
                QgsField("notas", _FIELD_STRING),
            ]
        )
        molde.updateFields()

        # Escribir la capa vacía al .gpkg. Como el archivo no existe,
        # writeAsVectorFormatV3 lo crea desde cero con la tabla pedida.
        opciones = QgsVectorFileWriter.SaveVectorOptions()
        opciones.driverName = "GPKG"
        opciones.layerName = GPKG_TABLE

        # Asegurar que el directorio destino exista (por si la ruta apunta
        # a una subcarpeta que aún no se ha creado).
        os.makedirs(
            os.path.dirname(os.path.abspath(self.gpkg_path)) or ".",
            exist_ok=True,
        )

        QgsVectorFileWriter.writeAsVectorFormatV3(
            molde,
            self.gpkg_path,
            QgsCoordinateTransformContext(),
            opciones,
        )

        # La tabla annotation_notes no es espacial, así que la creamos
        # directamente con sqlite3 una vez que el .gpkg ya existe en disco.
        self._asegurar_tabla_notas()

    # ── Operaciones sobre anotaciones ──────────────────────────────────────

    def agregar_anotacion(
        self,
        geometry: QgsGeometry,
        origin: str = "human",
        score: float = None,
    ) -> QgsFeature:
        """Agrega una anotación con estado 'pending' y la persiste al GPKG.

        Args:
            geometry: geometría poligonal de la anotación.
            origin: 'human' (dibujada por el usuario) o 'ml' (importada
                desde una detección automática).
            score: score de confianza (0..1). Solo aplica cuando origin='ml';
                para anotaciones humanas se guarda como NULL.

        Como la capa es GPKG-backed (provider 'ogr'), la llamada a
        dataProvider().addFeatures() escribe directamente al archivo en
        disco — no hace falta exportar/sobreescribir nada.
        """
        feature = QgsFeature(self.layer.fields())
        # Geometría del polígono dibujado o detectado.
        feature.setGeometry(geometry)
        feature.setAttribute("status", AnnotationState.PENDING.value)
        feature.setAttribute("origin", origin)
        feature.setAttribute("score", score)
        feature.setAttribute("timestamp", datetime.now(timezone.utc).isoformat())

        # addFeatures devuelve (ok, features_agregados); la 2ª contiene los
        # features con el fid ya asignado por el provider.
        ok, agregados = self.layer.dataProvider().addFeatures([feature])
        if not ok:
            raise RuntimeError("No se pudo persistir la anotación al GPKG")

        # Refrescar bbox y repintar el canvas.
        self.layer.updateExtents()
        self.layer.triggerRepaint()

        # Devolver el feature ya con su fid asignado.
        return agregados[0] if agregados else feature

    def agregar_desde_mascara(self, mask, confidence: float = None, transform=None) -> "QgsFeature":
        # Convierte una máscara SAM a polígono y lo persiste como anotación.
        # Recibe un array 2D devuelto por SAM (mask), un score de confianza del modelo (score)
        # y un affine de rasterio para georreferenciar, si es None las coordenadas quedan en pixeles (transform)
        # Devuelve  El QgsFeature creado con origin='ml-annotation' y status='pending'.
        try:
            from .mask_to_polygon import mask_to_geojson_polygon
        except (ImportError, SystemError):
            try:
                from mask_to_polygon import mask_to_geojson_polygon
            except ImportError:
                mask_to_geojson_polygon = None

        if mask_to_geojson_polygon is None:
            raise ValueError("mask_to_polygon no está disponible en este entorno.")
        # 1. Convertir máscara a GeoJSON
        geojson_feature = mask_to_geojson_polygon(mask, transform=transform, origin="ml-annotation")

        # 2. Extraer coordenadas del polígono GeoJSON y convertir a QgsGeometry
        coords = geojson_feature["geometry"]["coordinates"][0]
        puntos = [QgsPointXY(x, y) for x, y in coords]
        geometry = QgsGeometry.fromPolygonXY([puntos])

        # 3. Persistir usando el método existente
        return self.agregar_anotacion(geometry, origin="ml-annotation", score=confidence)

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

    def pendiente_anotacion(self, feature_id: int) -> bool:
        """Cambia el status del feature a 'pending' y persiste el cambio.

        Útil para devolver una anotación approved/rejected a revisión.
        Lanza StateTransitionError si la transición no es válida (p.ej.
        intentar poner en pending algo que ya está pending).
        """
        return self._cambiar_estado(feature_id, AnnotationState.PENDING)

    def _cambiar_estado(self, feature_id: int, nuevo_estado: AnnotationState) -> bool:
        """Helper interno: valida la transición, actualiza atributos y persiste.

        El método público (aprobar / rechazar) decide el estado destino;
        este método se encarga de la lógica genérica que aplica a cualquier
        cambio de estado. Como la capa es GPKG-backed, changeAttributeValues
        escribe directo al archivo .gpkg.
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

        ok = self.layer.dataProvider().changeAttributeValues(
            {
                feature_id: {
                    idx_status: nuevo_estado.value,
                    idx_timestamp: nuevo_ts,
                }
            }
        )
        if not ok:
            return False

        # Refrescar la visualización (los datos ya se persistieron en disco).
        self.layer.triggerRepaint()
        return True

    # TIGS-87: Historial de notas por polígono con trazabilidad ─────────────

    def _asegurar_tabla_notas(self) -> None:
        """Crea la tabla annotation_notes si no existe.

        Es idempotente gracias a CREATE TABLE IF NOT EXISTS: se puede llamar
        en GPKGs nuevos (creación) y en GPKGs existentes (migración automática).
        No usa QGIS ni OGR — opera directamente sobre el archivo SQLite.
        """
        conn = sqlite3.connect(self.gpkg_path)
        try:
            conn.execute(_DDL_ANNOTATION_NOTES)
            conn.execute(_DDL_ANNOTATION_NOTES_INDEX)
            conn.commit()
        finally:
            conn.close()

    def agregar_nota(
        self,
        annotation_id: int,
        texto: str,
        origen: str = None,
        estado: str = None,
        score: float = None,
    ) -> bool:
        """Agrega una nueva entrada al historial de notas de un polígono.

        Nunca sobreescribe notas anteriores: cada llamada inserta una fila
        nueva en annotation_notes. Eso garantiza la trazabilidad completa
        requerida por CENIA.

        Args:
            annotation_id: fid del feature en la capa annotations.
            texto: contenido textual de la nota.
            origen: 'ml-annotation' o 'human-annotation'. Si no se pasa, se
                lee del feature en la capa (campo 'origin').
            estado: 'pending', 'approved' o 'rejected'. Si no se pasa, se
                lee del feature (campo 'status') para capturar el estado
                *al momento de escribir* la nota.
            score: score de confianza al momento de escribir la nota. Si no
                se pasa, se lee del feature (campo 'score').

        Returns:
            True si la nota se guardó correctamente.
        """
        if not texto:
            return True  # nada que guardar

        # Leer atributos del feature si no se pasaron explícitamente.
        if origen is None or estado is None or score is None:
            feat = self.layer.getFeature(annotation_id)
            if feat.isValid():
                if origen is None:
                    raw = feat.attribute("origin")
                    origen = str(raw) if raw is not None and raw != NULL else "human-annotation"
                if estado is None:
                    raw = feat.attribute("status")
                    estado = str(raw) if raw is not None and raw != NULL else "pending"
                if score is None:
                    raw = feat.attribute("score")
                    if raw is not None and raw != NULL:
                        try:
                            score = float(raw)
                        except (TypeError, ValueError):
                            score = None

        origen = origen or "human-annotation"
        estado = estado or "pending"
        timestamp = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(self.gpkg_path)
        try:
            conn.execute(
                "INSERT INTO annotation_notes "
                "(annotation_id, texto, origen, estado, score, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?);",
                (annotation_id, texto, origen, estado, score, timestamp),
            )
            conn.commit()
        finally:
            conn.close()
        return True

    def leer_historial_notas(self, annotation_id: int) -> list:
        """Retorna el historial completo de notas de un polígono.

        Orden cronológico ascendente (más antigua primero). Cada elemento
        es un dict con claves: id, texto, origen, estado, score, timestamp.
        Retorna lista vacía si no hay notas o si el .gpkg no tiene aún la
        tabla (GPKGs muy antiguos antes de esta versión).
        """
        try:
            conn = sqlite3.connect(self.gpkg_path)
            try:
                rows = conn.execute(
                    "SELECT id, texto, origen, estado, score, timestamp "
                    "FROM annotation_notes "
                    "WHERE annotation_id = ? "
                    "ORDER BY timestamp ASC;",
                    (annotation_id,),
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.OperationalError:
            # La tabla no existe en este GPKG (migración pendiente).
            return []
        return [
            {
                "id": r[0],
                "texto": r[1],
                "origen": r[2],
                "estado": r[3],
                "score": r[4],
                "timestamp": r[5],
            }
            for r in rows
        ]

    # TIGS 69 (compat): las funciones guardar_notas / leer_notas se mantienen
    # para no romper código existente. Internamente delegan al historial.

    def guardar_notas(self, feature_id: int, notas: str) -> bool:
        """Compatibilidad: agrega 'notas' como nueva entrada en el historial.

        No sobreescribe entradas anteriores; simplemente delega a agregar_nota().
        Si 'notas' está vacío no hace nada.
        """
        return self.agregar_nota(feature_id, notas)

    def leer_notas(self, feature_id: int) -> str:
        """Compatibilidad: retorna el texto de la nota más reciente del historial.

        Retorna string vacío si no hay notas.
        """
        historial = self.leer_historial_notas(feature_id)
        if historial:
            return historial[-1]["texto"]
        return ""

    # ── Estilo visual ──────────────────────────────────────────────────────

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
            categorias.append(QgsRendererCategory(estado.value, simbolo, estado.value))

        renderer = QgsCategorizedSymbolRenderer("status", categorias)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    # ── Exportar ──────────────────────────────────────────────────────
    def exportar_anotaciones_geojson(self, parent=None) -> str | None:
        """Exporta todas las anotaciones con status='approved'
        a un archivo GeoJSON estándar.

        Cada feature incluye:
            - geometría
            - origin
            - notas
            - score
            - timestamp"""

        # 1. Pedir ruta destino al usuario
        output_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Exportar anotaciones",
            "annotations.geojson",
            "GeoJSON (*.geojson *.json)",
        )

        # Usuario canceló
        if not output_path:
            return None

        # Asegurar extensión
        if not output_path.endswith((".geojson", ".json")):
            output_path += ".geojson"

        # 2. Obtener solo annotations approved
        approved_features = []

        for feature in self.layer.getFeatures():
            status = feature.attribute("status")

            if status != AnnotationState.APPROVED.value:
                continue

            geom_json = json.loads(feature.geometry().asJson())

            approved_features.append(
                {
                    "type": "Feature",
                    "geometry": geom_json,
                    "properties": {
                        "origin": (None if feature.attribute("origin") == NULL else str(feature.attribute("origin"))),
                        "notas": (None if feature.attribute("notas") == NULL else str(feature.attribute("notas"))),
                        "score": (None if feature.attribute("score") == NULL else float(feature.attribute("score"))),
                        "timestamp": (
                            None if feature.attribute("timestamp") == NULL else str(feature.attribute("timestamp"))
                        ),
                    },
                }
            )

        # 3. Construir FeatureCollection GeoJSON
        geojson = {
            "type": "FeatureCollection",
            "features": approved_features,
        }

        # 4. Guardar archivo
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)

        return output_path
