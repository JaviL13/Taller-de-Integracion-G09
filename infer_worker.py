# -*- coding: utf-8 -*-
"""
infer_worker.py — TIGS-53

Worker asíncrono que envía el ROI al endpoint POST /infer del backend
FastAPI usando urllib.

Diseño:
  - Se hereda de QThread (igual que `EnhanceWorker` de TIGS-42) para no
    bloquear el hilo principal de QGIS.
    - Dentro de `run()` se ejecuta la petición HTTP en el propio hilo de
        trabajo usando `urllib.request`.
  - Se exponen señales `finished(int, float, dict)` y `error(str)` para
    comunicar el resultado al hilo principal de Qt (signals/slots son
    thread-safe en Qt).

Manejo de fallos (degradación controlada — DoD TIGS-53):
  - Si el backend está apagado / inalcanzable     → emite `error`.
  - Si el backend devuelve HTTP != 200             → emite `error`.
    - Si la respuesta no es JSON parseable           → emite `error`.
  En todos los casos el worker termina limpio sin propagar excepciones
  al hilo principal: la herramienta de anotación manual sigue disponible.
"""

import json
import time
import urllib.error
import urllib.request

from qgis.PyQt.QtCore import QThread, pyqtSignal


class InferWorker(QThread):
    """QThread que ejecuta POST /infer con urllib.

    Signals:
        finished(int, float, dict): status HTTP, segundos transcurridos, body
        error(str): mensaje legible para mostrar al usuario.

    Args:
        bbox: lista de 4 floats [x1, y1, x2, y2] en el CRS del raster.
        image_path: ruta del archivo fuente del raster (puede ser None).
        crs_epsg: EPSG numérico del CRS del bbox (puede ser None).
        base_url: URL base del backend FastAPI. Por defecto coincide con la
            que usa EnhanceWorker (TIGS-42) para que ambos workers apunten
            al mismo servidor sin configuración duplicada.
        parent: parent Qt (opcional).
    """

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(int, float, dict)
    error = pyqtSignal(str)

    # Tiempo máximo total que el worker espera al backend. Coherente con
    # EnhanceWorker para que el usuario tenga la misma expectativa de UX.
    TIMEOUT_SECONDS = 30

    def __init__(
        self,
        bbox,
        image_path=None,
        crs_epsg=None,
        base_url="http://127.0.0.1:8000",
        parent=None,
    ):
        super().__init__(parent)
        # URL completa del endpoint /infer. Al concatenar con base_url se
        # respeta la misma convención que EnhanceWorker (`{base}/enhance`).
        self.url = f"{base_url}/infer"

        # Payload con el contrato InferRequest del backend (TIGS-49):
        #   bbox        -> list[float] (4 valores)
        #   image_path  -> Optional[str]
        #   crs_epsg    -> Optional[int]
        # Las claves opcionales se omiten cuando son None para no enviar
        # nulls al backend (algunos parsers Pydantic son estrictos).
        payload = {"bbox": list(bbox)}
        if image_path is not None:
            payload["image_path"] = image_path
        if crs_epsg is not None:
            payload["crs_epsg"] = int(crs_epsg)
        self.payload = payload

    # ------------------------------------------------------------------ #
    # QThread entry point                                                #
    # ------------------------------------------------------------------ #

    def run(self):
        """Punto de entrada del hilo: ejecuta la petición HTTP."""
        self._post_infer()

    # ------------------------------------------------------------------ #
    # Llamada HTTP                                                       #
    # ------------------------------------------------------------------ #

    def _post_infer(self):
        """Ejecuta el POST al endpoint /infer.

        Toda la lógica de errores está aquí dentro: se traduce cada
        excepción a una señal `error(str)` legible. Nunca se propaga una
        excepción fuera del worker.
        """
        self.progress.emit(0, 1)
        start = time.time()
        try:
            data = json.dumps(self.payload).encode("utf-8")
            req = urllib.request.Request(
                self.url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT_SECONDS) as resp:
                elapsed = time.time() - start
                raw = resp.read().decode("utf-8")

                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    self.error.emit("Respuesta inesperada del backend (no es JSON válido).")
                    return

                self.progress.emit(1, 1)
                self.finished.emit(resp.status, elapsed, body)

        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")

            try:
                body = json.loads(body_text)
            except json.JSONDecodeError:
                self.error.emit(f"HTTP {e.code}: {body_text[:200]}")
                return

            detail = body.get("detail") if isinstance(body, dict) else None
            self.error.emit(f"HTTP {e.code}: {detail or str(body)[:200]}")

        except TimeoutError:
            self.error.emit(f"Timeout: el backend no respondió en {self.TIMEOUT_SECONDS}s.")

        except Exception as e:  # noqa: BLE001
            # Captura general para no dejar excepciones sueltas en el hilo.
            self.error.emit(f"Backend no disponible en {self.url} — {type(e).__name__}: {e}")
