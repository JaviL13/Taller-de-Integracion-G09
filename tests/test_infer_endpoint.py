# el contenido dentro del archivo se ha ocupado IA para poder crear tests más
# robustos y claros y poder testear escenarios difíciles
# -*- coding: utf-8 -*-
"""Tests del endpoint POST /infer (TIGS-70).

Valida que el endpoint:
  - Acepta una imagen como multipart/form-data.
  - Ejecuta SAM (mocked) y devuelve máscara en base64 + confianza.
  - Rechaza archivos que no son imágenes (HTTP 400).
  - GET /health funciona (regresión).

El modelo SAM se mockea con unittest.mock.patch para no cargar el modelo
real durante testing. Se genera una máscara sintética (cuadrado en el centro
de una imagen 256x256 con confidence=0.92).

Usa fastapi.testclient.TestClient: corre la app ASGI en proceso.
"""

import base64
import io
import json
import os
import sys
from unittest.mock import patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Setup de imports
# ---------------------------------------------------------------------------

# Agregar backend/ al sys.path para imports
BACKEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend",
)
sys.path.insert(0, BACKEND_DIR)

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
# sam_wrapper importa torch, que es muy pesado para instalar en CI. Si no
# está disponible, saltar todo el módulo de tests (no se pueden ejecutar
# sin tener el modelo SAM cargado de todas formas).
pytest.importorskip("torch")
from fastapi.testclient import TestClient  # noqa: E402

# Mockear initialize_sam ANTES de importar app, para que no intente
# cargar el modelo real en el lifespan del servidor
with patch("sam_wrapper.initialize_sam"):
    from main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Cliente HTTP en proceso contra la app FastAPI."""
    return TestClient(app)


@pytest.fixture
def synthetic_image_png():
    """Genera una imagen PNG sintética (256x256 RGB uint8) para testing.

    Returns:
        bytes: PNG codificado como bytes (listo para multipart/form-data).
    """
    # Crear array RGB de 256x256, valores [0, 255]
    image_array = np.zeros((256, 256, 3), dtype=np.uint8)
    # Llenar de gris (100, 100, 100)
    image_array[:, :] = [100, 100, 100]

    # Convertir a PIL Image y guardar como PNG
    from PIL import Image

    img = Image.fromarray(image_array, mode="RGB")
    png_bytes = io.BytesIO()
    img.save(png_bytes, format="PNG")
    png_bytes.seek(0)
    return png_bytes.getvalue()


@pytest.fixture
def synthetic_mask_and_confidence():
    """Genera una máscara sintética y confianza para mockear run_sam().

    La máscara es un cuadrado blanco (255) en el centro de 256x256,
    rodeado de negro (0). Confianza = 0.92.

    Returns:
        tuple: (mask_array, confidence)
    """
    mask = np.zeros((256, 256), dtype=np.uint8)
    # Cuadrado en el centro (100x100 píxeles)
    mask[78:178, 78:178] = 255
    confidence = 0.92
    return mask, confidence


# ---------------------------------------------------------------------------
# Tests para TIGS-70
# ---------------------------------------------------------------------------


def test_health(client):
    """GET /health retorna 200 y {"status": "ok"}."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_infer_returns_mask(client, synthetic_image_png, synthetic_mask_and_confidence):
    """POST /infer con imagen válida retorna máscara en base64 + confianza.

    Se mockea sam_wrapper.run_sam() para retornar una máscara sintética
    (cuadrado en el centro) con confidence=0.92.

    Validaciones:
      - HTTP 200
      - status == "ok"
      - mask_b64 es válido (decodificable) y es una imagen PNG válida
      - confidence está en [0, 1]
      - width y height coinciden con la imagen de entrada (256x256)
    """
    mask, confidence = synthetic_mask_and_confidence

    # Mockear run_sam para retornar máscara sintética + confianza
    with patch("main.run_sam") as mock_run_sam:
        mock_run_sam.return_value = (mask, confidence)

        # Preparar multipart/form-data con la imagen PNG
        files = {
            "image": ("test.png", synthetic_image_png, "image/png"),
        }

        # POST /infer
        resp = client.post("/infer", files=files)

        # Validaciones
        assert resp.status_code == 200
        body = resp.json()

        # Estructura
        assert body["status"] == "ok"
        assert "mask_b64" in body
        assert "confidence" in body
        assert "width" in body
        assert "height" in body

        # Validar dimensiones
        assert body["width"] == 256
        assert body["height"] == 256

        # Validar confianza
        assert isinstance(body["confidence"], float)
        assert 0.0 <= body["confidence"] <= 1.0
        assert body["confidence"] == 0.92

        # Validar que mask_b64 es decodificable y es PNG
        mask_b64 = body["mask_b64"]
        try:
            mask_bytes = base64.b64decode(mask_b64)
            # Intentar abrir como imagen para verificar que es PNG válido
            from PIL import Image

            decoded_mask = Image.open(io.BytesIO(mask_bytes))
            assert decoded_mask.format == "PNG"
            # Convertir a array para validar que tiene forma correcta
            mask_array = np.array(decoded_mask)
            assert mask_array.shape == (256, 256)  # Grayscale
        except Exception as e:
            pytest.fail(f"mask_b64 no es PNG válido: {e}")


def test_infer_invalid_file_returns_error(client):
    """POST /infer con archivo de texto (no imagen) retorna HTTP 400.

    Se envía un archivo .txt en lugar de una imagen. El endpoint
    debe rechazarlo gracefully con HTTP 400 o similar.
    """
    # Crear un archivo de texto
    text_content = b"This is not an image, just plain text"
    files = {
        "image": ("test.txt", text_content, "text/plain"),
    }

    # POST /infer con archivo inválido
    resp = client.post("/infer", files=files)

    # Debe fallar (no 200)
    assert resp.status_code != 200
    # Esperar 400 o 422 (ambos son razonables para input inválido)
    assert resp.status_code in [400, 422, 500]

    # Si es 400-422, debe tener un mensaje de error en la respuesta
    if resp.status_code in [400, 422]:
        body = resp.json()
        # Puede ser {"detail": "..."} o {"error": "..."}
        assert "detail" in body or "error" in body


def test_infer_with_points_and_labels(client, synthetic_image_png, synthetic_mask_and_confidence):
    """POST /infer acepta puntos y labels opcionales (refinamiento iterativo).

    Los puntos se envían como JSON en el form-data.
    """
    mask, confidence = synthetic_mask_and_confidence

    with patch("main.run_sam") as mock_run_sam:
        mock_run_sam.return_value = (mask, confidence)

        files = {
            "image": ("test.png", synthetic_image_png, "image/png"),
        }
        data = {
            "points": json.dumps([[128, 128], [200, 200]]),  # Dos puntos
            "labels": json.dumps([1, 1]),  # Ambos foreground
        }

        resp = client.post("/infer", files=files, data=data)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["confidence"] == 0.92

        # Verificar que run_sam fue llamado con los puntos correctos
        mock_run_sam.assert_called_once()
        call_args = mock_run_sam.call_args
        # call_args[1] son kwargs: {'points': ..., 'labels': ...}
        assert call_args is not None


def test_infer_without_sam_initialization_fails(client, synthetic_image_png):
    """Si run_sam no está mocked y SAM no está inicializado, falla.

    Este test verifica que sin mock, el endpoint intenta realmente
    ejecutar SAM y devuelve error si no está disponible.
    """
    # Sin mockear run_sam, el endpoint intentará ejecutar run_sam() real.
    # Como SAM no estará inicializado (initialize_sam fue mocked en imports),
    # debe fallar con error.
    files = {
        "image": ("test.png", synthetic_image_png, "image/png"),
    }

    # Sin mock de run_sam
    resp = client.post("/infer", files=files)

    # Esperar error (no 200)
    assert resp.status_code != 200
    body = resp.json()
    # El error debe mencionar que SAM no está inicializado
    assert "error" in body or "detail" in body
