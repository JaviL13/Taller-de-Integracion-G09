# Tests unitarios de mask_to_polygon.py (TIGS-71).
# Valida que la conversión de máscara binaria SAM a polígono GeoJSON:
# Produce geometría válida para una máscara simple,
# Incluye las propiedades 'origin' y 'status' correctas.
# Falla con ValueError para máscaras vacías o con forma incorrecta.
# Acepta transform personalizado (georreferenciación).
# Selecciona el polígono más grande cuando hay varios contornos.

import os
import sys

import numpy as np
import pytest
from rasterio.transform import Affine
from shapely.geometry import shape

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mask_to_polygon import mask_to_geojson_polygon

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cuadrado_mask(h=64, w=64, margen=10):
    """Máscara binaria con un cuadrado blanco centrado."""
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[margen : h - margen, margen : w - margen] = 255
    return mask


# ---------------------------------------------------------------------------
# Tests: caso exitoso
# ---------------------------------------------------------------------------


def test_mascara_simple_produce_geojson_valido():
    """Una máscara con cuadrado central produce un Feature GeoJSON válido."""
    mask = _cuadrado_mask()
    resultado = mask_to_geojson_polygon(mask)

    assert resultado["type"] == "Feature"
    assert "geometry" in resultado
    assert "properties" in resultado


def test_geometria_es_poligono():
    """El tipo de geometría debe ser Polygon o MultiPolygon."""
    mask = _cuadrado_mask()
    resultado = mask_to_geojson_polygon(mask)
    geom_type = resultado["geometry"]["type"]
    assert geom_type in ("Polygon", "MultiPolygon")


def test_geometria_shapely_es_valida():
    """La geometría debe ser válida según shapely (sin auto-intersecciones)."""
    mask = _cuadrado_mask()
    resultado = mask_to_geojson_polygon(mask)
    geom = shape(resultado["geometry"])
    assert geom.is_valid
    assert not geom.is_empty


def test_propiedades_origin_y_status_presentes():
    """El Feature debe tener 'origin' y 'status' en properties."""
    mask = _cuadrado_mask()
    resultado = mask_to_geojson_polygon(mask)
    props = resultado["properties"]
    assert "origin" in props
    assert "status" in props


def test_status_es_pending_por_defecto():
    """El status por defecto debe ser 'pending'."""
    mask = _cuadrado_mask()
    resultado = mask_to_geojson_polygon(mask)
    assert resultado["properties"]["status"] == "pending"


def test_origin_por_defecto_es_ml_annotation():
    """El origin por defecto debe ser 'ml-annotation'."""
    mask = _cuadrado_mask()
    resultado = mask_to_geojson_polygon(mask)
    assert resultado["properties"]["origin"] == "ml-annotation"


def test_origin_personalizado():
    """Se puede pasar un origin distinto."""
    mask = _cuadrado_mask()
    resultado = mask_to_geojson_polygon(mask, origin="human-annotation")
    assert resultado["properties"]["origin"] == "human-annotation"


def test_coordenadas_en_pixeles_sin_transform():
    """Sin transform, las coordenadas deben estar en espacio píxel (0..N)."""
    mask = _cuadrado_mask(64, 64, margen=10)
    resultado = mask_to_geojson_polygon(mask)
    geom = shape(resultado["geometry"])
    minx, miny, maxx, maxy = geom.bounds
    # Las coordenadas deben estar dentro del rango de la imagen
    assert 0 <= minx and maxx <= 64
    assert 0 <= miny and maxy <= 64


def test_con_transform_afin_coordenadas_georreferenciadas():
    """Con un Affine transform, las coordenadas deben ser georreferenciadas."""
    mask = _cuadrado_mask(64, 64, margen=10)
    # Transform que traslada a coordenadas UTM ficticias
    transform = Affine(0.5, 0, 500000, 0, -0.5, 7500000)
    resultado = mask_to_geojson_polygon(mask, transform=transform)
    geom = shape(resultado["geometry"])
    minx, _, maxx, _ = geom.bounds
    # Las coordenadas X deben estar cerca de 500000 (UTM Este)
    assert minx >= 500000


# ---------------------------------------------------------------------------
# Tests: selección del polígono principal
# ---------------------------------------------------------------------------


def test_selecciona_poligono_mas_grande():
    """Si hay varios contornos, debe retornar el de mayor área."""
    mask = np.zeros((100, 100), dtype=np.uint8)
    # Cuadrado grande: 60x60
    mask[10:70, 10:70] = 255
    # Cuadrado pequeño: 5x5
    mask[80:85, 80:85] = 255

    resultado = mask_to_geojson_polygon(mask)
    geom = shape(resultado["geometry"])
    # El área del polígono grande es ~3600, el pequeño ~25
    assert geom.area > 100


# ---------------------------------------------------------------------------
# Tests: errores controlados
# ---------------------------------------------------------------------------


def test_mascara_vacia_lanza_value_error():
    """Máscara completamente negra (sin detecciones) debe lanzar ValueError."""
    mask = np.zeros((64, 64), dtype=np.uint8)
    with pytest.raises(ValueError, match="vacía"):
        mask_to_geojson_polygon(mask)


def test_mascara_1d_lanza_value_error():
    """Máscara 1D (forma incorrecta) debe lanzar ValueError."""
    mask = np.ones((64,), dtype=np.uint8) * 255
    with pytest.raises(ValueError):
        mask_to_geojson_polygon(mask)


def test_mascara_none_lanza_value_error():
    """Pasar None como máscara debe lanzar ValueError."""
    with pytest.raises(ValueError):
        mask_to_geojson_polygon(None)


def test_mascara_3d_lanza_value_error():
    """Máscara RGB (3D) debe lanzar ValueError — se espera 2D."""
    mask = np.ones((64, 64, 3), dtype=np.uint8) * 255
    with pytest.raises(ValueError):
        mask_to_geojson_polygon(mask)
