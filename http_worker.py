# -*- coding: utf-8 -*-
"""
Worker asíncrono para comunicación HTTP con el backend FastAPI de GeoGlyph.
Usa QThread para no bloquear el hilo principal de QGIS.
"""
from qgis.PyQt.QtCore import QThread, pyqtSignal
import urllib.request
import urllib.error
import json
import time


class EnhanceWorker(QThread):
    """
    Worker que ejecuta POST /enhance en un hilo separado.

    Signals:
        finished(int, float, dict): status HTTP, segundos transcurridos, body JSON
        error(str): mensaje de error legible para mostrar en la UI
    """

    finished = pyqtSignal(int, float, dict)
    error = pyqtSignal(str)

    TIMEOUT_SECONDS = 30

    def __init__(
            self,
            base_url="http://localhost:8000",
            bbox=None,
            band=1,
            parent=None):
        super().__init__(parent)
        self.url = f"{base_url}/enhance"
        self.payload = {
            "bbox": bbox if bbox is not None else [0, 0, 100, 100],
            "band": band,
        }

    def run(self):
        """Ejecuta la llamada HTTP. Corre en el hilo secundario."""
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
                body = json.loads(resp.read().decode("utf-8"))
                self.finished.emit(resp.status, elapsed, body)

        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            self.error.emit(f"HTTP {e.code}: {body_text[:200]}")

        except urllib.error.URLError as e:
            self.error.emit(
                f"Backend no disponible en {self.url} — {e.reason}"
            )

        except TimeoutError:
            self.error.emit(
                f"Timeout: el backend no respondió en {self.TIMEOUT_SECONDS}s"
            )

        except json.JSONDecodeError:
            self.error.emit(
                "Respuesta inesperada del backend (no es JSON válido)")

        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Error inesperado: {type(e).__name__}: {e}")
