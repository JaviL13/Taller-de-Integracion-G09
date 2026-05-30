# -*- coding: utf-8 -*-
"""
raster_crop.py — TIGS-53, TIGS-70

Utilidades para extraer un recorte (crop) del raster activo dado un
QgsRectangle de ROI seleccionado por el usuario.

Diseño:
  - `extract_raster_crop(layer, rect)` devuelve un dict con:
        bbox       lista de 4 floats [x1, y1, x2, y2] en el CRS del raster
        image_path ruta del archivo fuente del raster (para trazabilidad)
        crs_epsg   EPSG numérico del CRS del raster (None si no se puede inferir)
        pixels_w   ancho en píxeles del recorte (referencial)
        pixels_h   alto en píxeles del recorte (referencial)

  - `extract_raster_pixels(layer, rect)` (TIGS-70) devuelve la imagen real
    como np.ndarray de forma (H, W, 3) [0, 255] uint8 RGB.

  El recorte real (los bytes del raster) NO se envía al endpoint /infer
  porque la versión actual del contrato (TIGS-49) sólo recibe metadatos
  (bbox + image_path + crs_epsg). Se calcula el ancho/alto en píxeles
  para fines de logging/debug y para que quede preparado el día que el
  endpoint pase a aceptar bytes binarios.
"""

import os
from typing import Optional

import numpy as np
from qgis.core import (
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
)

MAX_ROI_PIXELS = 2048

def extract_raster_crop(layer: QgsRasterLayer, rect: QgsRectangle) -> dict:
    """Extrae los metadatos del recorte de un raster dada una ROI.

    Args:
        layer: Capa raster activa de QGIS sobre la que se hizo la selección.
        rect:  QgsRectangle con la ROI dibujada en coordenadas del CRS del
               canvas (puede diferir del CRS del raster).

    Returns:
        dict con bbox, image_path, crs_epsg y dimensiones en píxeles del
        recorte. Las claves coinciden con el contrato InferRequest del
        backend (TIGS-49) para poder pasar el dict directamente a aiohttp.

    Raises:
        ValueError: si la ROI no intersecta el raster (selección fuera de la
            imagen) o si la capa no es válida.
    """
    if layer is None or not isinstance(layer, QgsRasterLayer):
        raise ValueError("La capa activa no es un raster válido.")

    # ------------------------------------------------------------------ #
    # 1. Reproyectar la ROI al CRS del raster                             #
    # ------------------------------------------------------------------ #
    # El usuario puede tener el canvas en un CRS distinto del raster
    # (ej. canvas en EPSG:3857 y raster en EPSG:32719). Para que el bbox
    # tenga sentido sobre el raster, se reproyecta al CRS del raster.
    raster_crs = layer.crs()
    canvas_crs = QgsProject.instance().crs()

    if canvas_crs != raster_crs:
        transform = QgsCoordinateTransform(canvas_crs, raster_crs, QgsCoordinateTransformContext())
        roi_in_raster_crs = transform.transformBoundingBox(rect)
    else:
        # Mismo CRS: no hace falta reproyectar.
        roi_in_raster_crs = QgsRectangle(rect)

    # ------------------------------------------------------------------ #
    # 2. Validar intersección con la extensión del raster                #
    # ------------------------------------------------------------------ #
    # Si el usuario seleccionó fuera de la imagen, el bbox no tiene
    # sentido y el endpoint devolvería un polígono inválido.
    if not roi_in_raster_crs.intersects(layer.extent()):
        raise ValueError("La ROI seleccionada no intersecta el raster activo.")

    # Recortar al área válida del raster — evita enviar coords fuera de
    # la imagen al backend.
    roi_clipped = roi_in_raster_crs.intersect(layer.extent())

    # ------------------------------------------------------------------ #
    # 3. Calcular dimensiones del recorte en píxeles                     #
    # ------------------------------------------------------------------ #
    # No es info crítica para el endpoint mock pero útil para log/debug
    # y para validar que el recorte tenga tamaño razonable (>0 píxeles).
    provider = layer.dataProvider()
    raster_w = provider.xSize()  # ancho en píxeles
    raster_h = provider.ySize()  # alto en píxeles

    # Resolución por píxel (units/pixel) en cada eje.
    extent = layer.extent()
    px_per_unit_x = raster_w / extent.width() if extent.width() > 0 else 0
    px_per_unit_y = raster_h / extent.height() if extent.height() > 0 else 0

    pixels_w = max(1, int(round(roi_clipped.width() * px_per_unit_x)))
    pixels_h = max(1, int(round(roi_clipped.height() * px_per_unit_y)))

    # Validar que el ROI no supere el límite máximo procesable por SAM.
    if pixels_w > MAX_ROI_PIXELS or pixels_h > MAX_ROI_PIXELS:
        raise ValueError(
            f"El ROI seleccionado es demasiado grande ({pixels_w}x{pixels_h} px). "
            f"El límite máximo es {MAX_ROI_PIXELS}x{MAX_ROI_PIXELS} px. "
            "Selecciona una región más pequeña."
        )
    # ------------------------------------------------------------------ #
    # 4. Inferir EPSG y path del archivo fuente                          #
    # ------------------------------------------------------------------ #
    crs_epsg: Optional[int] = None
    auth_id = raster_crs.authid()  # ej "EPSG:32719"
    if auth_id and auth_id.upper().startswith("EPSG:"):
        try:
            crs_epsg = int(auth_id.split(":", 1)[1])
        except ValueError:
            crs_epsg = None

    # `source()` devuelve la ruta del archivo en disco (o un URI más
    # complejo si la capa viene de WMS/PG). Lo usamos como image_path en
    # la request — el backend puede usarlo si está montado en la misma
    # máquina, o ignorarlo en el caso del mock.
    image_path = layer.source() or None

    return {
        "bbox": [
            roi_clipped.xMinimum(),
            roi_clipped.yMinimum(),
            roi_clipped.xMaximum(),
            roi_clipped.yMaximum(),
        ],
        "image_path": image_path,
        "crs_epsg": crs_epsg,
        "pixels_w": pixels_w,
        "pixels_h": pixels_h,
    }


def extract_raster_pixels(layer: QgsRasterLayer, rect: QgsRectangle) -> np.ndarray:
    """Extrae los píxeles del raster en el ROI especificado (TIGS-70).

    Devuelve un array numpy de forma (H, W, 3) con valores uint8 [0, 255]
    correspondiendo a la imagen RGB recortada. Se reprojecta automáticamente
    el ROI al CRS del raster si es necesario.

    Args:
        layer: Capa raster de QGIS.
        rect:  QgsRectangle con la ROI en coordenadas del canvas.

    Returns:
        np.ndarray de forma (H, W, 3) uint8 RGB.

    Raises:
        ValueError: si no hay intersección o si la capa no es válida.
    """
    if layer is None or not isinstance(layer, QgsRasterLayer):
        raise ValueError("La capa activa no es un raster válido.")

    # Reproyectar ROI al CRS del raster (igual que en extract_raster_crop)
    raster_crs = layer.crs()
    canvas_crs = QgsProject.instance().crs()

    if canvas_crs != raster_crs:
        transform = QgsCoordinateTransform(canvas_crs, raster_crs, QgsCoordinateTransformContext())
        roi_in_raster_crs = transform.transformBoundingBox(rect)
    else:
        roi_in_raster_crs = QgsRectangle(rect)

    # Validar intersección
    if not roi_in_raster_crs.intersects(layer.extent()):
        raise ValueError("La ROI seleccionada no intersecta el raster activo.")

    roi_clipped = roi_in_raster_crs.intersect(layer.extent())

    # QGIS puede devolver URIs con parámetros extra; para rasterio necesitamos
    # una ruta local real al archivo fuente.
    source_path = (layer.source() or "").split("|", 1)[0].strip()
    if not source_path or not os.path.exists(source_path):
        raise ValueError("No se pudo leer el archivo fuente del raster. Solo se admiten capas raster locales para SAM.")

    # Rasterio lee el recorte directamente desde el archivo fuente usando el
    # bounding box en coordenadas del CRS del raster.
    try:
        try:
            import rasterio
            from rasterio.enums import Resampling
            from rasterio.windows import from_bounds
        except ImportError as exc:
            raise ValueError(
                "rasterio no está instalado en el entorno de QGIS. Instálalo para extraer el ROI del raster."
            ) from exc

        with rasterio.open(source_path) as src:
            window = from_bounds(
                roi_clipped.xMinimum(),
                roi_clipped.yMinimum(),
                roi_clipped.xMaximum(),
                roi_clipped.yMaximum(),
                transform=src.transform,
            )

            band_count = src.count
            if band_count >= 3:
                data = src.read(
                    indexes=[1, 2, 3],
                    window=window,
                    out_shape=(3, max(1, int(round(window.height))), max(1, int(round(window.width)))),
                    resampling=Resampling.nearest,
                    boundless=True,
                    fill_value=0,
                )
                image_array = np.transpose(data, (1, 2, 0))
            else:
                data = src.read(
                    indexes=1,
                    window=window,
                    out_shape=(max(1, int(round(window.height))), max(1, int(round(window.width)))),
                    resampling=Resampling.nearest,
                    boundless=True,
                    fill_value=0,
                )
                image_array = np.stack([data, data, data], axis=2)

            # Asegurar uint8 para el backend SAM.
            if image_array.dtype != np.uint8:
                image_array = np.clip(image_array, 0, 255).astype(np.uint8)

    except Exception as e:
        raise ValueError(f"Error leyendo píxeles del raster: {e}") from e

    return image_array
