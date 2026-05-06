# Backend — Inferencia MobileSAM

Este README describe cómo preparar y ejecutar el backend FastAPI que usa MobileSAM (implementación ligera de SAM) para servir el endpoint `/infer` utilizado por el plugin GeoGlyph.

Requisitos y recomendaciones
- Python 3.8+
- Entorno virtual (`venv` o `conda`) recomendado
- Si dispone de GPU NVIDIA y quiere aceleración, instale drivers NVIDIA y CUDA compatibles antes de instalar PyTorch
- Asegúrese de tener herramientas nativas necesarias para `rasterio`/GDAL (ej. `brew install gdal` en macOS o `sudo apt install gdal-bin libgdal-dev` en Ubuntu)

Pasos rápidos

1) Crear y activar entorno virtual

```bash
cd backend
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```

2) Instalar PyTorch (elige según GPU/CPU)

- GPU (NVIDIA): siga las instrucciones de https://pytorch.org/get-started/locally/ y elija la rueda que coincide con su versión de CUDA.
- CPU-only (ejemplo):

```bash
pip install "torch>=2.2.2" "torchvision>=0.17.2" --index-url https://download.pytorch.org/whl/cpu
```

Instalar PyTorch antes de las demás dependencias ayuda a evitar ruedas incompatibles.

3) Instalar dependencias del backend

```bash
pip install -r requirements.txt
```

Nota: `backend/requirements.txt` contiene una referencia a MobileSAM (`mobile-sam @ https://github.com/ChaoningZhang/MobileSAM/...`) que será descargada desde GitHub.

4) (Opcional) Usar checkpoint local

- Cree `backend/models/` y coloque el checkpoint del modelo allí.
- Edite `backend/sam_wrapper.py` y ajuste `MODEL_PATH` por la ruta relativa al checkpoint (por ejemplo `models/mobilesam_checkpoint.pth`).

5) Ejecutar servidor

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Endpoints útiles
- `http://localhost:8000/health`
- `http://localhost:8000/info`
- `http://localhost:8000/docs`

Prueba rápida del endpoint `/infer`

```bash
curl -X POST "http://localhost:8000/infer" -F "image=@/ruta/a/tu/roi.png" -s | jq .
```

Notas para QGIS / el plugin
- El intérprete de Python que usa QGIS debe tener instalado `httpx` para que `sam_client.py` pueda enviar solicitudes al backend desde QGIS.
- Si QGIS usa un entorno Python independiente, instale `httpx` dentro de ese entorno.

Problemas comunes
- Instalación de `rasterio`/GDAL: instale las librerías nativas del sistema antes de crear el entorno virtual si pip falla al compilar ruedas.
- macOS Apple Silicon (M1/M2): use ruedas y builds compatibles; consulte las páginas oficiales de PyTorch y OpenCV.
- GPU: asegúrese de que los drivers y la versión de CUDA coincidan con la rueda de PyTorch instalada.

Uso en desarrollo
- Conecte el plugin GeoGlyph a `http://localhost:8000` en el panel de configuración.
- Si el backend no está disponible, el plugin sigue funcionando con las funcionalidades no dependientes de inferencia.

Contacto
- Para dudas sobre el backend o problemas de dependencias, consulte `backend/main.py` y `backend/sam_wrapper.py`.
