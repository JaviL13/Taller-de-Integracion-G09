## TIGS-53 — Selección de ROI sobre el mapa QGIS y envío al backend

Implementa la funcionalidad descrita en TIGS-53 (S3-06) del Sprint 3.

### Qué hace

- Agrega un botón **"Seleccionar ROI (rect)"** al panel lateral de GeoGlyph.
- Activa una herramienta `QgsMapTool` que permite dibujar un rectángulo
  sobre el canvas arrastrando el mouse (feedback visual con `QgsRubberBand`
  semi-transparente verde).
- Al soltar el clic, extrae los metadatos del recorte del raster activo
  (bbox reproyectado al CRS del raster, image_path, EPSG, dimensiones en
  píxeles) y los envía de forma asíncrona al endpoint `POST /infer` usando
  `aiohttp` en un `QThread` dedicado, sin bloquear el hilo principal de QGIS.
- Si el backend no responde, muestra un `QMessageBox` de aviso y un mensaje
  rojo en el label de estado **pero NO desactiva la anotación manual**
  (degradación controlada — DoD).

### Archivos nuevos

| Archivo | Descripción |
|---|---|
| `roi_select_tool.py` | `RectangularROITool(QgsMapTool)` — selección rectangular con press/move/release y soporte de Esc para cancelar. |
| `raster_crop.py` | `extract_raster_crop(layer, rect)` — reproyecta la ROI al CRS del raster, valida intersección con el extent y arma el payload del endpoint `/infer`. |
| `infer_worker.py` | `InferWorker(QThread)` — POST async con `aiohttp` en un event loop dedicado al hilo. Maneja timeout, backend caído, JSON inválido y `aiohttp` no instalado. |

### Archivos modificados

- `geoglyph.py`: nuevos imports, estado `_roi_tool` / `_infer_worker`, conexión del botón, callbacks `_activar_herramienta_roi`, `_on_roi_seleccionado`, `_on_infer_ok`, `_on_infer_error`. Limpieza del worker en `unload()`.
- `geoglyph_panel.py`: nuevo botón `btn_roi` en la sección de Anotaciones.
- `requirements.txt`: agrega `aiohttp`.

### Cómo probarlo

1. `pip install aiohttp` en el entorno de QGIS.
2. Levantar el backend con el endpoint `/infer` (TIGS-49):
   ```bash
   git worktree add /tmp/backend-tigs49 origin/feature/TIGS-49-infer-endpoint
   cd /tmp/backend-tigs49/backend && uvicorn main:app --reload --port 8000
   ```
3. Reiniciar QGIS / activar el plugin GeoGlyph.
4. Abrir un GeoTIFF (botón "Abrir GeoTIFF") y dejarlo seleccionado.
5. Apretar **"Seleccionar ROI (rect)"** y arrastrar sobre el raster.
6. El label de estado debe pasar de naranja ("enviando...") a verde con
   `HTTP 200 · 1 det · score=0.87 · modelo=sam_mock_v0`.

**Casos de error a verificar:**
- Backend apagado → `QMessageBox` de aviso; el botón "Dibujar polígono" sigue funcionando.
- ROI fuera del raster → mensaje "ROI no intersecta el raster".
- Click sin arrastrar → mensaje "Selección inválida".
- Esc durante la selección → rubber band se borra sin enviar nada.

### Dependencias

- **TIGS-49 (S3-04)** — endpoint `POST /infer` (en `feature/TIGS-49-infer-endpoint`, aún no merged a develop). El plugin funciona aunque el endpoint no esté: simplemente entra el camino de degradación.
- **TIGS-43 (S3-01)** — `PolygonDrawTool` y `AnnotationManager` (ya en develop). La nueva herramienta sigue el mismo patrón y comparte el panel.

### DoD

- [x] Pasa `ruff check` y `ruff format --check` (línea 120) en los 3 archivos nuevos.
- [x] Docstrings en todas las clases/métodos principales.
- [x] Comentarios inline explicando reproyección de CRS, lifecycle del worker y degradación controlada.
- [x] PR abierto hacia `develop`.
- [ ] Página de Notion (la abro al mergear).

Refs: TIGS-53
