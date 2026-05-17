# el contenido dentro del archivo se ha ocupado IA para poder aplicar técnicas más
# específicas y poder resolver errores de código que advertía la consola de qgis
# para activar entorno virtual ejecutar dentro de backend
# python -m venv venv
# venv\Scripts\activate

import base64
import io
import json
import sys

# para generar el timestamp de la respuesta
import time
from contextlib import asynccontextmanager

# para generar el timestamp de la respuesta
from datetime import datetime
from typing import Optional

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

# valida automáticamente los datos que llegan al endpoint
from pydantic import BaseModel, field_validator

# Importar el wrapper de SAM
from sam_wrapper import initialize_sam, run_sam

# ── Startup del servidor: cargar el modelo SAM UNA SOLA VEZ ────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan de FastAPI: inicializa SAM al startup y limpia al shutdown."""
    # Startup
    print("[STARTUP] Inicializando modelo MobileSAM...")
    try:
        initialize_sam()
        print("[STARTUP] ✓ Modelo SAM cargado exitosamente")
    except Exception as e:
        print(f"[STARTUP] ✗ Error cargando SAM: {e}")
        raise

    yield  # La aplicación corre aquí

    # Cleanup (opcional — SAM se limpia automáticamente)
    print("[SHUTDOWN] Limpiando recursos...")


app = FastAPI(lifespan=lifespan)  # crea el servidor


@app.get("/health")  # url, primer endpoint
def health():
    return {  # fastapi automáticamente lo convierte a json
        "status": "ok",
        "version": "1.0",
    }


@app.get("/info")  # url, segundo endpoint
def info():
    return {"python_version": sys.version}


# Define qué datos debe enviar el plugin al servidor para solicitar un realce


class EnhanceRequest(BaseModel):
    # lista de 4 números que representan las coordenadas
    bbox: list[float]
    band: int  # número de banda a procesar

    # Hay que verificar que bbox tenga exactamente 4 coordenadas
    # Si no, FastAPI responde automáticamente con error 422
    @field_validator("bbox")
    def bbox_debe_tener_4_valores(cls, v):
        if len(v) != 4:
            raise ValueError("bbox debe tener exactamente 4 valores: [x1, y1, x2, y2]")
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
        "processing_time_ms": round(processing_time_ms, 2),
    }


# ---------------------------------------------------------------------------
# POST /infer  (TIGS-70)
#
# Endpoint que recibe una imagen y opcionalmente puntos de prompt, ejecuta
# MobileSAM, y devuelve la máscara binaria en base64 + score de confianza.
#
# Entrada:
#   - image: archivo de imagen (multipart/form-data)
#   - points: opcional, JSON array de puntos [[x1, y1], [x2, y2], ...]
#   - labels: opcional, JSON array de labels [1, 1, ...] (1=foreground, 0=background)
#
# Salida:
#   - mask_b64: máscara binaria (PNG) codificada en base64
#   - confidence: float en [0, 1], score del modelo
#   - width, height: dimensiones de la imagen
# ---------------------------------------------------------------------------


class InferResponse(BaseModel):
    """Respuesta del endpoint /infer con máscara y confianza."""

    status: str
    mask_b64: str  # Máscara PNG en base64
    confidence: float
    width: int
    height: int
    processing_time_ms: float


@app.post("/infer", response_model=InferResponse)
async def infer(
    image: UploadFile = File(...),
    points: Optional[str] = Form(None),
    labels: Optional[str] = Form(None),
):
    """
    Ejecuta SAM sobre una imagen con puntos de prompt opcionales.

    Args:
        image: archivo de imagen (PNG, JPEG, etc.)
        points: JSON string con array de puntos [[x, y], ...] o None
        labels: JSON string con array de labels [1, 1, ...] o None
                Si no se pasa, todos los puntos son foreground (1)
    """
    inicio = time.time()

    # 1. Leer imagen del upload
    image_data = await image.read()
    try:
        image_pil = Image.open(io.BytesIO(image_data))
    except UnidentifiedImageError as e:
        print(f"[ERROR /infer] UnidentifiedImageError: {e}")
        raise HTTPException(status_code=400, detail="Archivo de imagen inválido")

    # Asegurar que es RGB (convertir si es RGBA, escala de grises, etc.)
    if image_pil.mode != "RGB":
        image_pil = image_pil.convert("RGB")

    image_array = np.array(image_pil)  # (H, W, 3)
    height, width = image_array.shape[:2]

    # 2. Parsear puntos y labels si se enviaron
    points_array = None
    labels_array = None

    if points is not None:
        try:
            points_list = json.loads(points)
            points_array = np.array(points_list, dtype=np.float32)
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=422, detail="Formato de 'points' inválido. Espera JSON: [[x1, y1], ...]")

    if labels is not None:
        try:
            labels_list = json.loads(labels)
            labels_array = np.array(labels_list, dtype=np.int32)
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=422, detail="Formato de 'labels' inválido. Espera JSON: [1, 1, ...]")

    # 3. Ejecutar SAM
    try:
        mask, confidence = run_sam(image_array, points=points_array, labels=labels_array)
    except Exception as e:
        print(f"[ERROR /infer] {type(e).__name__}: {e}")
        # Si el modelo no está inicializado, devolver 500
        raise HTTPException(status_code=500, detail=f"Error de inferencia: {type(e).__name__}: {str(e)[:200]}")

    # 4. Codificar máscara a PNG base64
    mask_pil = Image.fromarray(mask, mode="L")  # Máscara grayscale
    mask_bytes = io.BytesIO()
    mask_pil.save(mask_bytes, format="PNG")
    mask_b64 = base64.b64encode(mask_bytes.getvalue()).decode("utf-8")

    # 5. Armar respuesta
    processing_time_ms = (time.time() - inicio) * 1000
    
    return {
        "status": "ok",
        "mask_b64": mask_b64,
        "confidence": float(confidence),
        "width": width,
        "height": height,
        "processing_time_ms": processing_time_ms,
    }


# para ejecutar servidor:
# instalar dependencias: pip install -r requirements.txt
# Ejecutar: uvicorn main:app --reload
# debería poder abrir
# http://localhost:8000/health
# http://localhost:8000/info
# http://localhost:8000/enhance
# http://localhost:8000/infer
# En http://localhost:8000/docs se pueden revisar todos los endpoints
