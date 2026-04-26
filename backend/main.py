# para activar entorno virtual ejecutar dentro de backend
# python -m venv venv
# venv\Scripts\activate

from fastapi import FastAPI
import sys
# valida automáticamente los datos que llegan al endpoint
from pydantic import BaseModel, field_validator
# para generar el timestamp de la respuesta
from datetime import datetime, timezone
import time
from typing import Optional

app = FastAPI()  # crea el servidor


@app.get("/health")  # url, primer endpoint
def health():
    return {  # fastapi automáticamente lo convierte a json
        "status": "ok",
        "version": "1.0"
    }


@app.get("/info")  # url, segundo endpoint
def info():
    return {
        "python_version": sys.version
    }

# Define qué datos debe enviar el plugin al servidor para solicitar un realce


class EnhanceRequest(BaseModel):
    # lista de 4 números que representan las coordenadas
    bbox: list[float]
    band: int                                   # número de banda a procesar

    # Hay que verificar que bbox tenga exactamente 4 coordenadas
    # Si no, FastAPI responde automáticamente con error 422
    @field_validator('bbox')
    def bbox_debe_tener_4_valores(cls, v):
        if len(v) != 4:
            raise ValueError(
                'bbox debe tener exactamente 4 valores: [x1, y1, x2, y2]')
        return v


# Endpoint que recibe las coordenadas y la banda a realzar
@app.post("/enhance")
def enhance(request: EnhanceRequest):
    # Se registrará el tiempo de inicio para calcular cuánto tardó
    inicio = time.time()

    # En el futuro aquí iría la llamada al modelo de ML real
    timestamp = datetime.now().isoformat()

    # Calcular tiempo de procesamiento en milisegundos
    processing_time_ms = (time.time() - inicio) * 1000

    return {
        "status": "ok",
        "region_received": request.bbox,
        "timestamp": timestamp,
        "processing_time_ms": round(processing_time_ms, 2)
    }


# ---------------------------------------------------------------------------
# POST /infer  (TIGS-49)
#
# Endpoint que recibe una ROI (Region Of Interest) y devuelve una máscara
# mock + score de confianza. Permite que el cliente HTTP del plugin pueda
# integrarse end-to-end con el backend SIN tener SAM realmente conectado.
# La integración real con SAM se hará en otro ticket; este endpoint queda
# como contrato estable para que ambos lados puedan avanzar en paralelo.
# ---------------------------------------------------------------------------

# Identificador del modelo mock. Cuando se conecte SAM real, esta constante
# cambia (p.ej. "sam_vit_h_v1"). El valor se devuelve en cada respuesta y
# se persiste en el campo model_version del .gpkg (ver TIGS-45) para que el
# equipo pueda distinguir detecciones generadas durante desarrollo vs. las
# del modelo real.
INFER_MOCK_MODEL_VERSION = "sam_mock_v0"

# Score fijo del mock. Lo importante es que el cliente sepa parsearlo y
# mostrarlo en la UI; el valor real lo definirá SAM cuando llegue.
INFER_MOCK_CONFIDENCE = 0.87


class InferRequest(BaseModel):
    """ROI sobre la cual el cliente pide segmentación.

    bbox      coords del rectángulo [x1, y1, x2, y2] en el CRS del cliente.
    image_path opcional, ruta a la imagen procesada (trazabilidad y, cuando
              llegue SAM real, lo necesitará para abrir el archivo).
    crs_epsg  opcional, EPSG del CRS en que vienen las coords del bbox.
    """
    bbox: list[float]
    image_path: Optional[str] = None
    crs_epsg: Optional[int] = None

    # Hay que verificar que bbox tenga exactamente 4 coordenadas y que
    # x1 < x2, y1 < y2. Si no, FastAPI responde automáticamente con 422.
    @field_validator('bbox')
    def bbox_debe_ser_valido(cls, v):
        if len(v) != 4:
            raise ValueError(
                'bbox debe tener exactamente 4 valores: [x1, y1, x2, y2]')
        x1, y1, x2, y2 = v
        if x1 >= x2 or y1 >= y2:
            raise ValueError(
                'bbox inválido: se requiere x1 < x2 y y1 < y2')
        return v


class Detection(BaseModel):
    """Una máscara devuelta por el modelo.

    polygon    lista de [x, y] en el mismo CRS que el bbox de entrada.
               El polígono está cerrado (primer punto == último), que es
               lo que espera QgsGeometry.fromPolygonXY del cliente y lo
               que persiste el .gpkg.
    confidence score del modelo en [0, 1].
    """
    polygon: list[list[float]]
    confidence: float


class InferResponse(BaseModel):
    status: str
    detections: list[Detection]
    model_version: str
    timestamp: str
    processing_time_ms: float


def _generar_poligono_mock(bbox: list[float]) -> list[list[float]]:
    """Genera un rectángulo cerrado dentro del bbox, encogido al 50%.

    La forma es determinista (mismo input → mismo output) para que los
    tests puedan asertar la geometría exacta, y queda siempre dentro del
    bbox de entrada para que sea una anotación válida cuando el cliente
    la persista.
    """
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    # Cada lado del polígono mock = 50% del lado del bbox correspondiente.
    half_w = (x2 - x1) * 0.25
    half_h = (y2 - y1) * 0.25
    return [
        [cx - half_w, cy - half_h],
        [cx + half_w, cy - half_h],
        [cx + half_w, cy + half_h],
        [cx - half_w, cy + half_h],
        [cx - half_w, cy - half_h],  # cierra el anillo
    ]


# Endpoint /infer: recibe una ROI y devuelve una máscara mock con score.
@app.post("/infer", response_model=InferResponse)
def infer(request: InferRequest):
    inicio = time.time()

    polygon = _generar_poligono_mock(request.bbox)
    detections = [
        Detection(polygon=polygon, confidence=INFER_MOCK_CONFIDENCE),
    ]

    # ISO-8601 con sufijo Z explícito (UTC). datetime.utcnow() está
    # deprecated en Python 3.12, por eso se usa now(timezone.utc).
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    processing_time_ms = round((time.time() - inicio) * 1000, 2)

    return InferResponse(
        status="ok",
        detections=detections,
        model_version=INFER_MOCK_MODEL_VERSION,
        timestamp=timestamp,
        processing_time_ms=processing_time_ms,
    )

# para ejecutar servidor:
# instalar dependencias: pip install -r requirements.txt
# Ejecutar: uvicorn main:app --reload
# debería poder abrir
# http://localhost:8000/health
# http://localhost:8000/info
# http://localhost:8000/enhance
# http://localhost:8000/infer
# En http://localhost:8000/docs se pueden revisar todos los endpoints
