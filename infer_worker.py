from qgis.PyQt.QtCore import QThread, pyqtSignal
#Muy similar a http_worker
import urllib.request 
import urllib.error
import json
import time

class InferWorker(QThread):
    finished = pyqtSignal(int, float, list) #cuando todo sale bien la señal se emite con el codigo, tiempo y lista de detecciones
    error = pyqtSignal(str) 
    TIMEOUT_SECONDS = 30 #Si el backend no responde en 30 segundos es un error

    def __init__(self, base_url="http://localhost:8000", bbox=None, crs_epsg=None, parent=None):
        super().__init__(parent)
        self.url = f"{base_url}/infer"

        self.payload = {
            "bbox": bbox if bbox is not None else [0, 0, 100, 100],
            "crs_epsg": crs_epsg,
        }
    
    def run(self):
        start = time.time() #Cuando se empieza a calcular para saber cuánto tardó
        try:
            data = json.dumps(self.payload).encode("utf-8")
            req = urllib.request.Request(
                self.url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            ) #Construye petición HTTP POST
            with urllib.request.urlopen(req, timeout=self.TIMEOUT_SECONDS) as resp:
                elapsed = time.time() - start #envia la petición y calcula el tiempo
                body = json.loads(resp.read().decode("utf-8")) #convierte a texto
                self.finished.emit(resp.status, elapsed, body.get("detections", [])) #emite señal de finished
        
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            self.error.emit(f"HTTP {e.code}: {body_text[:200]}")

        except urllib.error.URLError as e:
            self.error.emit(f"Backend no disponible en {self.url} — {e.reason}")

        except TimeoutError:
            self.error.emit(f"Timeout: el backend no respondió en {self.TIMEOUT_SECONDS}s")

        except json.JSONDecodeError:
            self.error.emit("Respuesta inesperada del backend (no es JSON válido)")

        except Exception as e:
            self.error.emit(f"Error inesperado: {type(e).__name__}: {e}")