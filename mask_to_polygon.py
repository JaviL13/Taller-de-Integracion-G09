#  Convierte una máscara binaria devuelta por SAM a un polígono GeoJSON usando rasterio y shapely.

import numpy as np
import rasterio.features
from rasterio.transform import Affine
from shapely.geometry import shape

def mask_to_geojson_polygon(mask: np.ndarray, transform=None, origin: str = "ml-annotation") -> dict:
    # Convierte una máscara binaria SAM a un polígono GeoJSON.
    # Recibe un array 2D numpy mayor a 0, que isgnifica que detectó un geoglifo (mask), 
    # un affine de rasterio para georreferenciar coordenadas, si es none quedan en pixeles (transform),
    # y un string con nombre por defecto "ml-annotation" (origin)
    # Devuelve un GeoJSON con geometría de polígono y propiedas con origin de estados "pending"

    if mask is None or mask.ndim != 2:
        raise ValueError("La máscara debe ser un array 2D numpy.")

    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)

    binary = (mask > 0).astype(np.uint8)

    if binary.max() == 0:
        raise ValueError("La máscara está vacía — SAM no detectó ninguna región.")

    if transform is None:
        transform = Affine.identity()

    shapes = list(rasterio.features.shapes(binary, transform=transform))

    if not shapes:
        raise ValueError("No se encontraron contornos en la máscara.")

    poligonos = [shape(geom) for geom, value in shapes if value == 1.0]

    if not poligonos:
        raise ValueError("No se encontraron regiones activas en la máscara.")

    poligono_principal = max(poligonos, key=lambda p: p.area)

    return {
        "type": "Feature",
        "geometry": poligono_principal.__geo_interface__,
        "properties": {
            "origin": origin,
            "status": "pending",
        }
    }