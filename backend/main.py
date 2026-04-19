# para activar entorno virtual ejecutar dentro de backend
# python -m venv venv
# venv\Scripts\activate

from fastapi import FastAPI
import sys

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

# para ejecutar servidor:
# instalar dependencias: pip install -r requirements.txt
# Ejecutar: uvicorn main:app --reload
# debería poder abrir 
# http://localhost:8000/health
# http://localhost:8000/info
# En http://localhost:8000/docs se pueden revisar todos los endpoints