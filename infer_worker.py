# -*- coding: utf-8 -*-
"""
infer_worker.py — TIGS-53

Worker asíncrono que envía el ROI al endpoint POST /infer del backend
FastAPI usando aiohttp.

Diseño:
  - Se hereda de QThread (igual que `EnhanceWorker` de TIGS-42) para no
    bloquear el hilo principal de QGIS.
  - Dentro de `run()` se crea un event loop de asyncio propio del hilo y
    se ejecuta una corrutina que usa `aiohttp.ClientSession`.
  - Se exponen señales `finished(int, float, dict)` y `error(str)` para
    comunicar el resultado al hilo principal de Qt (signals/slots son
    thread-safe en Qt).

Manejo de fallos (degradación controlada — DoD TIGS-53):
  - Si el backend está apagado / inalcanzable     → emite `error`.
  - Si el backend devuelve HTTP != 200             → emite `error`.
  - Si la respuesta no es JSON parseable           → emite `error`.
  - Si aiohttp no está instalado en el QGIS host   → emite `error`.
  En todos los casos el worker termina limpio sin propagar excepciones
  al hilo principal: la herramienta de anotación manual sigue disponible.
"""

import asyncio
import json
import time

from qgis.PyQt.QtCore import QThread, pyqtSignal


class InferWorker(QThread):
    """QThread que ejecuta POST /infer con aiohttp.

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
        base_url="http://localhost:8000",
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
        """Punto de entrada del hilo: lanza el event loop asyncio.

        QThread llama a este método cuando se invoca `.start()`. Aquí se
        construye un event loop dedicado al hilo (no se puede reutilizar
        el loop del hilo principal de Qt) y se ejecuta la corrutina HTTP.
        """
        # Crear un event loop nuevo para este hilo. `new_event_loop` +
        # `set_event_loop` es el patrón estándar para usar asyncio dentro
        # de un QThread sin interferir con el loop principal.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._post_infer())
        finally:
            # Cerrar el loop SIEMPRE, incluso si _post_infer levantó algo
            # inesperado, para que el hilo no quede colgado.
            loop.close()

    # ------------------------------------------------------------------ #
    # Corrutina principal                                                #
    # ------------------------------------------------------------------ #

    async def _post_infer(self):
        """Ejecuta el POST asíncrono al endpoint /infer.

        Toda la lógica de errores está aquí dentro: se traduce cada
        excepción de aiohttp/asyncio a una señal `error(str)` legible.
        Nunca se propaga una excepción fuera de la corrutina (el llamador
        es `run()` que no debería ver fallos).
        """
        # Importación tardía: aiohttp no es dependencia core del plugin
        # QGIS y puede no estar instalado en todos los hosts. Mejor
        # detectar el ImportError aquí y emitir un error legible que
        # crashear al cargar el módulo.
        try:
            import aiohttp
        except ImportError:
            self.error.emit("aiohttp no está instalado en el entorno de QGIS. Ejecuta: pip install aiohttp")
            return

        start = time.time()
        try:
            # ClientTimeout cubre conexión + lectura. Si el backend acepta
            # la conexión pero no responde, se aborta a los TIMEOUT_SECONDS.
            timeout = aiohttp.ClientTimeout(total=self.TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.url,
                    json=self.payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    elapsed = time.time() - start
                    raw = await resp.text()

                    # Intentar parsear JSON aunque el status sea != 200,
                    # porque FastAPI devuelve detalles de error en JSON.
                    try:
                        body = json.loads(raw)
                    except json.JSONDecodeError:
                        self.error.emit("Respuesta inesperada del backend (no es JSON válido).")
                        return

                    # Caso éxito: 2xx → emit finished con el body parseado.
                    if 200 <= resp.status < 300:
                        self.finished.emit(resp.status, elapsed, body)
                        return

                    # Caso HTTP != 2xx: error legible con detalle del backend.
                    detail = body.get("detail") if isinstance(body, dict) else None
                    self.error.emit(f"HTTP {resp.status}: {detail or str(body)[:200]}")

        except asyncio.TimeoutError:
            # asyncio.TimeoutError es lo que dispara aiohttp cuando se
            # agota ClientTimeout — más específico que "Backend caído".
            self.error.emit(f"Timeout: el backend no respondió en {self.TIMEOUT_SECONDS}s.")

        except Exception as e:  # noqa: BLE001
            # Captura general para no dejar excepciones sueltas en el
            # hilo. aiohttp lanza varios tipos: ClientConnectorError,
            # ClientResponseError, etc. — todos se reportan al usuario
            # como "backend no disponible" y se conserva el tipo en el
            # mensaje para facilitar debugging.
            self.error.emit(f"Backend no disponible en {self.url} — {type(e).__name__}: {e}")
