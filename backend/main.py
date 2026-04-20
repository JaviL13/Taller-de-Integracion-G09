# para activar entorno virtual ejecutar dentro de backend
# python -m venv venv
# venv\Scripts\activate

from fastapi import FastAPI
import sys
from pydantic import BaseModel, field_validator   # valida automáticamente los datos que llegan al endpoint
from datetime import datetime                     # para generar el timestamp de la respuesta
import time                                       

app = FastAPI() # crea el servidor

@app.get("/health") # url, primer endpoint
def health():
    return { # fastapi automáticamente lo convierte a json
        "status": "ok",
        "version": "1.0"
    }

@app.get("/info") # url, segundo endpoint
def info():
    return {
        "python_version": sys.version
    }

# Define qué datos debe enviar el plugin al servidor para solicitar un realce
class EnhanceRequest(BaseModel):
    bbox: list[float]                           # lista de 4 números que representan las coordenadas
    band: int                                   # número de banda a procesar

    # Hay que verificar que bbox tenga exactamente 4 coordenadas
    # Si no, FastAPI responde automáticamente con error 422
    @field_validator('bbox')
    def bbox_debe_tener_4_valores(cls, v):
        if len(v) != 4:
            raise ValueError('bbox debe tener exactamente 4 valores: [x1, y1, x2, y2]')
        return v

@app.post("/enhance")                           # Endpoint que recibe las coordenadas y la banda a realzar
def enhance(request: EnhanceRequest):
    inicio = time.time()                        # Se registrará el tiempo de inicio para calcular cuánto tardó

    # En el futuro aquí iría la llamada al modelo de ML real
    timestamp = datetime.now().isoformat()

    processing_time_ms = (time.time() - inicio) * 1000      # Calcular tiempo de procesamiento en milisegundos

    return {
        "status": "ok",
        "region_received": request.bbox,
        "timestamp": timestamp,
        "processing_time_ms": round(processing_time_ms, 2)
    }

# para ejecutar servidor:
# instalar dependencias: pip install -r requirements.txt
# Ejecutar: uvicorn main:app --reload
# debería poder abrir 
# http://localhost:8000/health
# http://localhost:8000/info
# http://localhost:8000/enhance
# En http://localhost:8000/docs se pueden revisar todos los endpoints