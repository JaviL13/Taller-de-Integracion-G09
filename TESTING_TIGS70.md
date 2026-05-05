# Testing TIGS-70: Endpoint /infer con MobileSAM

## Instalación de dependencias

Para ejecutar los tests del endpoint `/infer`, necesitas instalar las dependencias de testing:

```bash
# Desde la raíz del proyecto
pip install -r requirements.txt  # Dependencias del plugin
pip install -r backend/requirements.txt  # Dependencias del backend
pip install pytest pytest-cov  # Testing framework
```

## Ejecutar los tests

```bash
# Todos los tests del endpoint /infer
pytest tests/test_infer_endpoint.py -v

# Test específico
pytest tests/test_infer_endpoint.py::test_health -v
pytest tests/test_infer_endpoint.py::test_infer_returns_mask -v
pytest tests/test_infer_endpoint.py::test_infer_invalid_file_returns_error -v

# Con cobertura
pytest tests/test_infer_endpoint.py --cov=backend --cov-report=html
```

## Tests implementados (TIGS-70)

### 1. `test_health()`
- Verifica que GET `/health` retorna HTTP 200
- Valida estructura de respuesta: `{"status": "ok", "version": "..."}`

### 2. `test_infer_returns_mask()`
- POST `/infer` con imagen PNG válida
- Mockea `sam_wrapper.run_sam()` con máscara sintética (cuadrado 100x100 en centro)
- Validaciones:
  - HTTP 200 OK
  - `status == "ok"`
  - `mask_b64` decodificable y es PNG válido
  - `confidence == 0.92` (en rango [0, 1])
  - `width` y `height` correctos (256x256)

### 3. `test_infer_invalid_file_returns_error()`
- POST `/infer` con archivo de texto (no imagen)
- Valida que rechaza gracefully con HTTP 400/422/500
- Verifica que la respuesta incluye un mensaje de error

### Tests adicionales
- `test_infer_with_points_and_labels()`: Verifica que el endpoint acepta puntos y labels opcionales
- `test_infer_without_sam_initialization_fails()`: Verifica comportamiento cuando SAM no está inicializado

## Mocking de SAM

Los tests mockean `sam_wrapper.initialize_sam()` y `main.run_sam()` para evitar:
- Cargar el modelo real (lento, requiere GPU/memoria)
- Tener dependencias de PyTorch/ONNX durante testing

Esto permite ejecutar los tests sin necesidad de descargar el modelo MobileSAM (~20 MB).

## Notas

- Los tests usan `unittest.mock.patch` para aislar el endpoint del modelo SAM
- Se generan imágenes y máscaras sintéticas (NumPy arrays) para testing
- El lifespan de FastAPI se mockea en imports para no fallar si SAM no está disponible
