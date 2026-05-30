# Worker que hace polling periódico al endpoint GET/health del backend
import urllib.error
import urllib.request

from qgis.PyQt.QtCore import QThread, pyqtSignal


class HealthWorker(QThread):
    # Polling periódico a GET/health.

    backend_up = pyqtSignal()  # El backend respondió correctamente
    backend_down = pyqtSignal(str)  # El backend no respondió (mensaje de error)

    TIMEOUT_SECONDS = 5

    def __init__(self, base_url="http://127.0.0.1:8000", interval_seconds=10, parent=None):
        super().__init__(parent)
        self.url = f"{base_url}/health"
        self.interval_seconds = interval_seconds
        self._running = True

    def stop(self):
        # Detiene el loop de polling.
        self._running = False

    def run(self):
        # Loop principal: pregunta al backend cada interval_seconds
        while self._running:
            try:
                req = urllib.request.Request(self.url, method="GET")
                with urllib.request.urlopen(req, timeout=self.TIMEOUT_SECONDS) as resp:
                    if resp.status == 200:
                        self.backend_up.emit()
                    else:
                        self.backend_down.emit(f"HTTP {resp.status}")
            except urllib.error.URLError as e:
                self.backend_down.emit(str(e.reason))
            except TimeoutError:
                self.backend_down.emit(f"Timeout ({self.TIMEOUT_SECONDS}s)")
            except Exception as e:
                self.backend_down.emit(f"{type(e).__name__}: {e}")

            self.msleep(self.interval_seconds * 1000)
