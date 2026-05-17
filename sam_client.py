# -*- coding: utf-8 -*-
"""
sam_client.py — TIGS-70

Worker asíncrono que envía una región recortada de la imagen al endpoint
POST /infer del backend FastAPI usando httpx en lugar de urllib.

Diseño:
  - Se hereda de QThread para no bloquear el hilo principal de QGIS.
  - Dentro de `run()` se ejecuta la petición HTTP en el hilo de trabajo.
  - Se exponen señales `finished(np.ndarray, float)` y `error(str)` para
    comunicar el resultado al hilo principal de Qt (thread-safe).

Diferencia con InferWorker (TIGS-53):
  - InferWorker envía el bbox como JSON y el backend genera un mock.
  - SamWorker (TIGS-70) envía la imagen como multipart/form-data y
    ejecuta MobileSAM realmente en el backend.

Flujo:
  1. El plugin llama a SamWorker(image_array, url, ...) con la imagen en píxeles.
  2. SamWorker transforma la imagen a PNG, la envía vía POST /infer.
  3. El backend ejecuta SAM, devuelve máscara en base64 + confianza.
  4. SamWorker decodifica la máscara y emite finished(mask, confidence).
  5. geoglyph.py recibe la señal y actualiza el panel con la confianza real.

Manejo de errores (degradación controlada):
  - Backend apagado / inalcanzable → emite error.
  - HTTP != 200 → emite error.
  - Respuesta no JSON parseable → emite error.
  - Timeout (30s) → emite error.
"""

import base64
import io
import json
import time
from typing import Optional

import numpy as np
from qgis.PyQt.QtCore import QBuffer, QIODevice, QThread, pyqtSignal
from qgis.PyQt.QtGui import QImage


class SamWorker(QThread):
    """QThread que ejecuta POST /infer con httpx y multipart/form-data.

    Signals:
        finished(np.ndarray, float): máscara binaria, confianza
        error(str): mensaje legible para mostrar al usuario.

    Args:
        image: np.ndarray de forma (H, W, 3) en [0, 255] (uint8) o [0, 1] (float).
        url: URL base del backend (p.ej. "http://localhost:8000").
        points: opcional, array de puntos [[x1, y1], ...] para refinamiento.
        labels: opcional, array de labels [1, 1, ...].
        parent: parent Qt (opcional).
    """

    finished = pyqtSignal(np.ndarray, float)
    error = pyqtSignal(str)

    # Timeout de 30 segundos (compatible con especificación TIGS-70)
    TIMEOUT_SECONDS = 30

    def __init__(
        self,
        image: np.ndarray,
        url: str = "http://localhost:8000",
        points: Optional[list] = None,
        labels: Optional[list] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.image = image  # np.ndarray (H, W, 3)
        self.url = f"{url}/infer"  # Endpoint completo
        self.points = points  # [[x, y], ...]
        self.labels = labels  # [1, 0, ...]

    def run(self):
        """Punto de entrada del hilo: ejecuta la petición HTTP."""
        self._post_infer()

    @staticmethod
    def _array_to_png_bytes(image_array: np.ndarray) -> bytes:
        """Convierte un array RGB uint8 a PNG bytes usando Qt."""
        if image_array.ndim != 3 or image_array.shape[2] != 3:
            raise ValueError("Se esperaba una imagen RGB de forma (H, W, 3)")

        image_array = np.ascontiguousarray(image_array, dtype=np.uint8)
        height, width, channels = image_array.shape
        bytes_per_line = channels * width
        qimage = QImage(
            image_array.tobytes(),
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888,
        ).copy()

        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        qimage.save(buffer, "PNG")
        return bytes(buffer.data())

    @staticmethod
    def _png_bytes_to_array(png_bytes: bytes) -> np.ndarray:
        """Convierte bytes PNG a array numpy en escala de grises usando Qt."""
        qimage = QImage.fromData(png_bytes, "PNG")
        if qimage.isNull():
            raise ValueError("No se pudo decodificar la máscara PNG")

        grayscale = qimage.convertToFormat(QImage.Format_Grayscale8)
        height = grayscale.height()
        width = grayscale.width()
        bytes_per_line = grayscale.bytesPerLine()

        ptr = grayscale.bits()
        ptr.setsize(grayscale.byteCount())
        array = np.frombuffer(ptr, dtype=np.uint8).reshape(height, bytes_per_line)
        return array[:, :width].copy()

    def _post_infer(self):
        """Ejecuta el POST al endpoint /infer con httpx.

        Toda la lógica de errores está aquí: se traduce cada excepción
        a una señal `error(str)` legible.
        """
        start = time.time()

        try:
            try:
                import httpx
            except ImportError:
                self.error.emit("httpx no está instalado en el entorno de QGIS. Instálalo para usar inferencia SAM.")
                return

            # Asegurar que es uint8 [0, 255]
            if self.image.dtype != np.uint8:
                if self.image.dtype in [np.float32, np.float64]:
                    # Si es float [0, 1], convertir a [0, 255]
                    if self.image.max() <= 1.0:
                        image_uint8 = (self.image * 255).astype(np.uint8)
                    else:
                        image_uint8 = self.image.astype(np.uint8)
                else:
                    image_uint8 = self.image.astype(np.uint8)
            else:
                image_uint8 = self.image

            # Crear imagen PNG sin depender de Pillow
            image_bytes = io.BytesIO(self._array_to_png_bytes(image_uint8))
            image_bytes.seek(0)

            # 2. Preparar multipart/form-data
            files = {
                "image": ("roi.png", image_bytes, "image/png"),
            }
            data = {}

            # Agregar puntos y labels si se proporcionaron
            if self.points is not None:
                data["points"] = json.dumps(np.asarray(self.points).tolist())
            if self.labels is not None:
                data["labels"] = json.dumps(np.asarray(self.labels).tolist())

            # 3. Ejecutar POST con httpx
            with httpx.Client(timeout=self.TIMEOUT_SECONDS) as client:
                response = client.post(self.url, files=files, data=data)
                # Tiempo medido para futuros logs de diagnóstico.
                _ = time.time() - start  # noqa: F841

                # 4. Validar respuesta
                if response.status_code != 200:
                    try:
                        body = response.json()
                        if isinstance(body, dict):
                            if "detail" in body:
                                error_msg = str(body["detail"])
                            else:
                                error_msg = body.get("error", str(body))
                        else:
                            error_msg = str(body)
                    except Exception:
                        error_msg = response.text[:200]
                    self.error.emit(f"HTTP {response.status_code}: {error_msg}")
                    return

                # 5. Parsear respuesta JSON
                try:
                    body = response.json()
                except json.JSONDecodeError:
                    self.error.emit("Respuesta del backend no es JSON válido")
                    return

                # 6. Validar estructura de respuesta
                if body.get("status") != "ok":
                    error_msg = body.get("error", "Status no es ok")
                    self.error.emit(f"Backend error: {error_msg}")
                    return

                # 7. Decodificar máscara desde base64
                try:
                    mask_b64 = body.get("mask_b64", "")
                    mask_bytes = base64.b64decode(mask_b64)
                    mask_array = self._png_bytes_to_array(mask_bytes)

                    confidence = float(body.get("confidence", 0.0))

                    # Emitir señal de éxito en el hilo principal
                    self.finished.emit(mask_array, confidence)

                except Exception as e:
                    self.error.emit(f"Error decodificando máscara: {e}")
                    return

        except TimeoutError:
            self.error.emit(f"Timeout: el backend no respondió en {self.TIMEOUT_SECONDS}s")

        except httpx.RequestError as e:
            # Backend no disponible, timeout, error de red, etc.
            self.error.emit(f"Backend no disponible en {self.url} — {type(e).__name__}: {str(e)[:100]}")

        except Exception as e:
            # Captura general para errores inesperados
            self.error.emit(f"Error inesperado: {type(e).__name__}: {str(e)[:100]}")
