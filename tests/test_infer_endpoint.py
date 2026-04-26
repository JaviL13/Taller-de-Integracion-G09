# -*- coding: utf-8 -*-
"""Tests de integración del endpoint POST /infer (TIGS-49).

Valida los criterios de aceptación:
  - El endpoint acepta una ROI (bbox) y devuelve una máscara mock.
  - La máscara es un polígono cerrado y queda dentro del bbox de entrada.
  - La respuesta incluye un score de confianza en [0, 1].
  - El cliente recibe un model_version que identifica que es mock
    (para que después se puedan distinguir detecciones de desarrollo
    vs. las del modelo real al revisar el .gpkg).
  - Inputs inválidos producen 422 (validación de pydantic).
  - /health y /enhance siguen funcionando (regresión).

Usa fastapi.testclient.TestClient: corre el ASGI app en proceso, no
necesita tener uvicorn levantado para correr los tests.
"""

import os
import sys

import pytest


# ---------------------------------------------------------------------------
# Setup de imports
# ---------------------------------------------------------------------------

# El paquete backend/ no tiene __init__.py (uvicorn lo corre como
# script desde dentro del directorio). Agregamos backend/ al sys.path
# para poder hacer "from main import app" desde el test.
BACKEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend",
)
sys.path.insert(0, BACKEND_DIR)

# fastapi.testclient depende de httpx. Si alguna de las dos no está,
# todos los tests del archivo se omiten en lugar de romper la suite
# (defensa en profundidad si alguien corre pytest sin instalar
# requirements.txt).
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


@pytest.fixture
def client():
    """Cliente HTTP en proceso contra la app FastAPI."""
    return TestClient(app)


# Bbox de prueba en EPSG:32719 (UTM 19S, Atacama). Rectángulo de 100×100 m.
BBOX_VALIDO = [500000.0, 7500000.0, 500100.0, 7500100.0]


# ---------------------------------------------------------------------------
# Happy path: estructura de la respuesta
# ---------------------------------------------------------------------------

def test_infer_returns_200(client):
    """Una ROI válida devuelve 200 OK."""
    resp = client.post("/infer", json={"bbox": BBOX_VALIDO})
    assert resp.status_code == 200


def test_infer_response_shape(client):
    """La respuesta debe traer los campos del contrato."""
    body = client.post("/infer", json={"bbox": BBOX_VALIDO}).json()
    assert body["status"] == "ok"
    assert "detections" in body
    assert "model_version" in body
    assert "timestamp" in body
    assert "processing_time_ms" in body
    assert isinstance(body["detections"], list)
    assert len(body["detections"]) >= 1


def test_infer_detection_tiene_polygon_y_confidence(client):
    """Cada detection debe tener polygon (lista de [x,y]) y confidence."""
    body = client.post("/infer", json={"bbox": BBOX_VALIDO}).json()
    detection = body["detections"][0]
    assert "polygon" in detection
    assert "confidence" in detection
    assert isinstance(detection["polygon"], list)
    assert isinstance(detection["confidence"], (int, float))


# ---------------------------------------------------------------------------
# Validación geométrica del polígono mock
# ---------------------------------------------------------------------------

def test_infer_polygon_es_cerrado(client):
    """El polígono debe ser un anillo cerrado (primer punto == último)."""
    body = client.post("/infer", json={"bbox": BBOX_VALIDO}).json()
    polygon = body["detections"][0]["polygon"]
    assert polygon[0] == polygon[-1], "El polígono debe estar cerrado"
    assert len(polygon) >= 4, "Polígono cerrado: mínimo 3 puntos + cierre"


def test_infer_polygon_dentro_del_bbox(client):
    """Todos los puntos del polígono caen dentro del bbox de entrada."""
    x1, y1, x2, y2 = BBOX_VALIDO
    body = client.post("/infer", json={"bbox": BBOX_VALIDO}).json()
    polygon = body["detections"][0]["polygon"]
    for x, y in polygon:
        assert x1 <= x <= x2, f"Punto x={x} fuera de bbox [{x1}, {x2}]"
        assert y1 <= y <= y2, f"Punto y={y} fuera de bbox [{y1}, {y2}]"


def test_infer_polygon_es_determinista(client):
    """Mismo input → mismo polígono. Permite asertar geometría en tests."""
    body1 = client.post("/infer", json={"bbox": BBOX_VALIDO}).json()
    body2 = client.post("/infer", json={"bbox": BBOX_VALIDO}).json()
    assert body1["detections"][0]["polygon"] == body2["detections"][0]["polygon"]


# ---------------------------------------------------------------------------
# Score y metadata
# ---------------------------------------------------------------------------

def test_infer_confidence_en_rango_valido(client):
    """confidence debe estar en [0, 1]."""
    body = client.post("/infer", json={"bbox": BBOX_VALIDO}).json()
    confidence = body["detections"][0]["confidence"]
    assert 0.0 <= confidence <= 1.0


def test_infer_model_version_declara_mock(client):
    """model_version debe declarar explícitamente que es mock.

    Cuando se persistan detecciones en el .gpkg (campo model_version
    del MER, ver TIGS-45), esto permite distinguir detecciones de
    desarrollo de las del modelo real.
    """
    body = client.post("/infer", json={"bbox": BBOX_VALIDO}).json()
    assert "mock" in body["model_version"].lower()


def test_infer_processing_time_no_negativo(client):
    """processing_time_ms debe existir y ser >= 0."""
    body = client.post("/infer", json={"bbox": BBOX_VALIDO}).json()
    assert body["processing_time_ms"] >= 0


def test_infer_acepta_image_path_y_crs_opcionales(client):
    """image_path y crs_epsg son opcionales pero deben aceptarse si vienen."""
    payload = {
        "bbox": BBOX_VALIDO,
        "image_path": "/data/cerro_unita.tif",
        "crs_epsg": 32719,
    }
    resp = client.post("/infer", json=payload)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Validación de input (errores 422)
# ---------------------------------------------------------------------------

def test_infer_bbox_con_3_valores_falla(client):
    """bbox de 3 valores debe fallar con 422."""
    resp = client.post("/infer", json={"bbox": [0, 0, 100]})
    assert resp.status_code == 422


def test_infer_bbox_invertido_falla(client):
    """bbox con x1 >= x2 debe fallar con 422."""
    resp = client.post("/infer", json={"bbox": [100, 0, 50, 100]})
    assert resp.status_code == 422


def test_infer_sin_bbox_falla(client):
    """Request sin bbox debe fallar con 422."""
    resp = client.post("/infer", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Regresión: endpoints existentes no deben romperse
# ---------------------------------------------------------------------------

def test_health_sigue_funcionando(client):
    """/health debe seguir respondiendo 200."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_enhance_sigue_funcionando(client):
    """/enhance no debe romperse al agregar /infer."""
    resp = client.post("/enhance", json={"bbox": [0, 0, 100, 100], "band": 1})
    assert resp.status_code == 200
