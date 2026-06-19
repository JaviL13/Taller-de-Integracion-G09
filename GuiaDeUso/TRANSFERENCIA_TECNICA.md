# GeoGlyph — Documento de Transferencia Técnica

> Proyecto de Título DCC — Grupo 09  
> Cliente: CENIA / EAA_UC  
> Versión: 1.0 | Junio 2026  
> Repositorio: https://github.com/JaviL13/Taller-de-Integracion-G09

Este documento está dirigido a cualquier equipo o persona que reciba, continúe o modifique el proyecto GeoGlyph. Complementa el documento de diseño y los READMEs de instalación: mientras esos documentos describen *qué se construyó*, este explica *por qué*, qué quedó pendiente, y qué hay que saber antes de tocar el código.

---

## Tabla de Contenidos

1. [Estado del sistema al momento de la entrega](#1-estado-del-sistema-al-momento-de-la-entrega)
2. [Decisiones de arquitectura](#2-decisiones-de-arquitectura)
3. [Modelo de segmentación: SAM 2](#3-modelo-de-segmentación-sam-2)
4. [Diccionario de datos (GeoPackage)](#4-diccionario-de-datos-geopackage)
5. [Deuda técnica y limitaciones conocidas](#5-deuda-técnica-y-limitaciones-conocidas)
6. [Cómo extender o reemplazar el modelo](#6-cómo-extender-o-reemplazar-el-modelo)
7. [Mapa de archivos clave](#7-mapa-de-archivos-clave)
8. [Contactos y accesos](#8-contactos-y-accesos)

---

## 1. Estado del sistema al momento de la entrega

La siguiente tabla resume el estado real de cada funcionalidad. La columna *Producción* indica si la funcionalidad está lista para uso por arqueólogos sin intervención del equipo de desarrollo.

| Funcionalidad | Estado | Producción | Notas |
|---|---|---|---|
| Carga de GeoTIFF y ortomosaicos | ✅ Completo | Sí | |
| Anotación manual de polígonos | ✅ Completo | Sí | |
| Estados de validación (pending / approved / rejected) | ✅ Completo | Sí | Visualización por color en QGIS |
| Notas e historial por anotación | ✅ Completo | Sí | Tabla `annotation_notes` |
| Exportación e importación GeoJSON | ✅ Completo | Sí | |
| Persistencia en GeoPackage (.gpkg) | ✅ Completo | Sí | Se genera al primer guardado |
| Vista side-by-side sincronizada | ✅ Completo | Sí | |
| Realce Color Ramp (Viridis / RdYlGn) | ✅ Completo | Sí | Procesamiento asíncrono |
| Realce DStretch | ✅ Completo | Sí | Recomendado sobre regiones pequeñas |
| Exportación de capa realzada | ⚠️ Funcional pero lento | Parcial | Puede tardar varios minutos en archivos grandes; excluido del demo |
| Backend FastAPI + SAM 2 | ✅ Completo | Sí (con backend levantado) | Ver sección 3 |
| Envío de ROI al backend (sam_client.py) | ✅ Completo | Sí | |
| Recepción de máscara y score | ✅ Completo | Sí | |
| **Renderización de máscara como polígono editable** | ❌ Pendiente | No | Ver sección 5 — este es el gap más importante |
| Health check / polling de estado del backend | ✅ Completo | Sí | |
| Pipeline CI/CD (lint + test + build) | ✅ Completo | Sí | GitHub Actions |
| Publicación de release automático (.zip) | ⚠️ Pendiente | No | Job `release` no implementado aún |

### Lo más importante a saber

El flujo de inferencia ML **está operativo de extremo a extremo**: el plugin envía la imagen al backend, SAM 2 genera una máscara, y el plugin recibe la máscara con su score de confianza. Lo que **no está terminado** es el paso final: convertir esa máscara binaria en un polígono vectorial visible y editable sobre el mapa de QGIS. El código de conversión (`mask_to_polygon.py`) existe y funciona de forma aislada, pero la integración con la capa de anotaciones de QGIS quedó pendiente para un sprint siguiente. Este es el principal trabajo que queda por hacer para cerrar el ciclo human-in-the-loop.

---

## 2. Decisiones de arquitectura

Esta sección documenta las decisiones de diseño no triviales tomadas durante el proyecto, con el razonamiento detrás de cada una. El objetivo es que un equipo nuevo no tenga que redescubrir estas conclusiones.

### 2.1 Plugin QGIS en lugar de aplicación web

**Decisión:** construir sobre QGIS (PyQGIS + PyQt5) en lugar de desarrollar una herramienta web independiente.

**Razón:** los arqueólogos de EAA_UC ya trabajan en QGIS. Reemplazar su entorno habitual habría implicado un proceso de adopción largo y resistencia al cambio. Al integrarse como plugin, el sistema extiende un flujo de trabajo existente sin interrumpirlo. QGIS además resuelve gratuitamente la visualización de GeoTIFFs de gran tamaño, la reproyección de coordenadas y el manejo de capas vectoriales, funcionalidades que habría costado meses replicar.

### 2.2 Backend desacoplado (FastAPI + SAM 2 separado del plugin)

**Decisión:** el modelo de ML no corre dentro de QGIS, sino en un servidor FastAPI separado que el plugin llama vía HTTP.

**Razón:** los modelos como SAM 2 requieren PyTorch y varios GB de dependencias que son incompatibles con el entorno Python embebido de QGIS. Además, el desacoplamiento permite que el backend corra en el clúster IALab de CENIA (con GPU) mientras el plugin corre en la laptop del arqueólogo. Si el backend no está disponible, el plugin opera sin degradarse: todas las funcionalidades de anotación manual siguen funcionando.

### 2.3 GeoPackage como formato de persistencia

**Decisión:** usar `.gpkg` (SQLite con extensiones geoespaciales) en lugar de PostGIS, Shapefile o GeoJSON para almacenar anotaciones.

**Razón:** GeoPackage es un archivo local, sin servidor, compatible con QGIS de forma nativa. Los arqueólogos pueden llevar sus anotaciones en un USB, abrirlas en cualquier máquina con QGIS, y compartirlas sin configurar una base de datos. PostGIS habría requerido infraestructura persistente que la contraparte no tiene. Shapefile tiene límites de longitud de nombre de campo y no soporta múltiples tablas relacionadas en un archivo. GeoJSON no tiene soporte nativo de relaciones FK ni índices eficientes.

### 2.4 httpx en lugar de urllib para las llamadas al backend

**Decisión:** `sam_client.py` usa `httpx` (cliente moderno con soporte `multipart/form-data`). El archivo `infer_worker.py` más antiguo todavía usa `urllib` y se mantiene por compatibilidad.

**Razón:** enviar la imagen como `multipart/form-data` con `urllib` requiere construir el payload manualmente, lo que era propenso a errores y difícil de testear. `httpx` lo resuelve en una línea. `infer_worker.py` no fue eliminado porque existían tests que dependían de él; en una próxima iteración puede removerse junto con sus tests.

### 2.5 Ruff en lugar de flake8 + black

**Decisión:** se migró de `flake8` a `ruff` como linter y formateador.

**Razón:** el código PyQGIS usa patrones que generan falsos positivos constantes en `flake8` (imports diferidos de Qt, comentarios con `#`, espaciado de alineación). `ruff` permite configurar esas excepciones por categoría en `ruff.toml` y ejecuta linting y formato en una sola herramienta, eliminando la necesidad de `black` por separado.

### 2.6 Una rama por tarea de Jira (no por línea de trabajo)

**Decisión:** cada tarea Jira (TIGS-XX) tiene su propia rama `feature/TIGS-XX-descripcion`, en lugar de ramas por área funcional (ej. `feature/backend`, `feature/ui`).

**Razón:** con 5 integrantes trabajando en paralelo sobre áreas que se solapan, las ramas por área generaban conflictos frecuentes y PRs difíciles de revisar. Una rama por tarea aisla los cambios, facilita la revisión y mantiene trazabilidad directa entre código y Jira.

---

## 3. Modelo de segmentación: SAM 2

### Qué es SAM 2

SAM 2 (*Segment Anything Model 2*) es el sucesor de SAM y MobileSAM, desarrollado por Meta AI. Ofrece mejor precisión que MobileSAM con soporte activo. El proyecto comenzó con MobileSAM y migró a SAM 2 durante el desarrollo por su mayor calidad de segmentación y por contar con una API de alto nivel más mantenida.

### Variante en uso

El backend usa `facebook/sam2.1-hiera-small`, descargado desde HuggingFace la primera vez que se levanta el servidor (~180 MB). Las ejecuciones siguientes usan la caché local de HuggingFace (`~/.cache/huggingface/`).

Otras variantes disponibles, en orden de velocidad/precisión:

| Modelo | Tamaño | Uso recomendado |
|--------|--------|-----------------|
| `facebook/sam2.1-hiera-tiny` | ~38 MB | Máquina sin GPU, desarrollo y testing |
| `facebook/sam2.1-hiera-small` | ~180 MB | **Uso actual — equilibrio velocidad/precisión** |
| `facebook/sam2.1-hiera-base-plus` | ~325 MB | Si se necesita mayor precisión con GPU disponible |
| `facebook/sam2.1-hiera-large` | ~900 MB | Máxima precisión, requiere GPU con ≥8 GB VRAM |

Para cambiar de variante, editar la constante `MODEL_HF_ID` en `backend/sam_wrapper.py`:

```python
# backend/sam_wrapper.py, línea 37
MODEL_HF_ID = "facebook/sam2.1-hiera-small"  # cambiar aquí
```

### Estrategia de prompt automático

Cuando el usuario no envía puntos de prompt (caso por defecto), el backend no usa simplemente el píxel central. Usa una estrategia más robusta:

- **5 puntos de foreground:** centro de la imagen + 4 puntos a 1/8 de distancia del centro en cada dirección cardinal.
- **4 puntos de background:** esquinas de la imagen con un margen interior del 5%.
- **Box prompt:** rectángulo que cubre el 70% central de la imagen, para reforzar dónde está el objeto.

Esta estrategia reduce el caso en que SAM 2 devuelve la imagen completa como máscara cuando el objeto ocupa poco espacio en el ROI.

### Requisitos de hardware del backend

- **CPU:** funciona, pero lento (~5–15 segundos por inferencia según tamaño del ROI).
- **GPU NVIDIA (CUDA):** recomendado para uso en producción (~0.5–2 segundos). El backend detecta la GPU automáticamente.
- **RAM mínima:** 8 GB (el modelo hiera-small carga ~2 GB en memoria).

---

## 4. Diccionario de datos (GeoPackage)

El archivo `.gpkg` generado por el plugin contiene cuatro tablas. Esta sección describe cada campo en lenguaje de dominio, pensada para arqueólogos o analistas que quieran trabajar directamente con el archivo en QGIS, Python o cualquier herramienta compatible con SQLite.

El archivo se llama `annotations.gpkg` y se genera en la carpeta del proyecto QGIS activo. No está versionado en el repositorio.

---

### Tabla `annotations`

Cada fila es un polígono creado en el plugin, ya sea manualmente o generado por el modelo.

| Campo | Tipo | Valores posibles | Descripción |
|-------|------|-----------------|-------------|
| `id` | INTEGER | Auto-incremental | Identificador único del polígono |
| `geom` | GEOMETRY | Polígono | Geometría georreferenciada del contorno del geoglifo, en el CRS del proyecto |
| `label` | TEXT | Libre | Etiqueta semántica asignada por el arqueólogo (ej. "geoglifo-línea", "geoglifo-figura") |
| `origin` | TEXT | `ml` / `human` | `ml`: polígono sugerido por el modelo SAM 2. `human`: polígono dibujado manualmente |
| `status` | TEXT | `pending` / `approved` / `rejected` | Estado de validación. `pending`: sin revisar; `approved`: aceptado por el arqueólogo; `rejected`: descartado |
| `confidence` | REAL | 0.0 – 1.0 o NULL | Score de confianza retornado por SAM 2. Solo tiene valor cuando `origin = 'ml'`; es NULL para anotaciones manuales |
| `notes` | TEXT | Libre o NULL | Nota más reciente asociada al polígono. Para el historial completo, consultar la tabla `annotation_notes` |
| `created_at` | TEXT | ISO 8601 | Fecha y hora de creación del polígono |
| `updated_at` | TEXT | ISO 8601 | Fecha y hora de la última modificación |
| `session_id` | INTEGER | FK → `sessions.id` | Sesión de trabajo en la que fue creado este polígono |
| `detection_id` | INTEGER | FK → `detections.id` o NULL | Vincula el polígono con una detección importada de origen externo. NULL si fue creado desde cero |

---

### Tabla `annotation_notes`

Historial completo de notas asociadas a cada polígono. Un polígono puede tener múltiples entradas a lo largo del tiempo.

| Campo | Tipo | Valores posibles | Descripción |
|-------|------|-----------------|-------------|
| `id` | INTEGER | Auto-incremental | Identificador único de la nota |
| `annotation_id` | INTEGER | FK → `annotations.id` | Polígono al que pertenece esta nota |
| `texto` | TEXT | Libre | Contenido de la nota |
| `origen` | TEXT | `ml` / `human` | Quién generó la nota: el modelo (`ml`) o el arqueólogo (`human`) |
| `estado` | TEXT | `pending` / `approved` / `rejected` | Estado del polígono en el momento en que se escribió la nota |
| `score` | REAL | 0.0 – 1.0 o NULL | Score de confianza al momento de la nota, si aplica |
| `timestamp` | TEXT | ISO 8601 | Fecha y hora en que se registró la nota |

---

### Tabla `sessions`

Cada vez que el usuario inicia una sesión de trabajo con el plugin se crea una fila aquí.

| Campo | Tipo | Valores posibles | Descripción |
|-------|------|-----------------|-------------|
| `id` | INTEGER | Auto-incremental | Identificador único de sesión |
| `started_at` | TEXT | ISO 8601 | Inicio de la sesión |
| `ended_at` | TEXT | ISO 8601 o NULL | Fin de la sesión. NULL si la sesión está activa o no se cerró correctamente |
| `image_path` | TEXT | Ruta de archivo | Ruta local al archivo GeoTIFF analizado en esta sesión |
| `model_version` | TEXT | Libre o NULL | Versión del modelo ML utilizado (ej. `sam2.1-hiera-small`) |
| `user` | TEXT | Libre o NULL | Usuario que realizó la sesión (no implementado aún, reservado para uso futuro) |

---

### Tabla `detections`

Candidatos generados por modelos externos e importados al plugin para su validación.

| Campo | Tipo | Valores posibles | Descripción |
|-------|------|-----------------|-------------|
| `id` | INTEGER | Auto-incremental | Identificador único de la detección |
| `geom` | GEOMETRY | Polígono | Geometría del candidato detectado |
| `confidence` | REAL | 0.0 – 1.0 | Score de confianza del modelo externo que generó esta detección |
| `priority` | TEXT | Libre o NULL | Nivel de prioridad de revisión asignado (ej. "alta", "media", "baja") |
| `model_version` | TEXT | Libre o NULL | Versión del modelo externo que generó la detección |
| `imported_at` | TEXT | ISO 8601 | Fecha y hora en que se importó esta detección |
| `session_id` | INTEGER | FK → `sessions.id` | Sesión en la que fue importada |

---

### Consultas útiles (SQLite / Python)

Para explorar el archivo fuera de QGIS, se puede abrir con cualquier cliente SQLite o con Python:

```python
import sqlite3

con = sqlite3.connect("annotations.gpkg")

# Todos los polígonos aprobados por el arqueólogo
con.execute("""
    SELECT id, label, confidence, created_at
    FROM annotations
    WHERE status = 'approved'
    ORDER BY created_at
""").fetchall()

# Historial de notas de un polígono específico
con.execute("""
    SELECT texto, origen, estado, timestamp
    FROM annotation_notes
    WHERE annotation_id = ?
    ORDER BY timestamp
""", (42,)).fetchall()

# Polígonos de origen ML con alta confianza aún sin revisar
con.execute("""
    SELECT id, confidence FROM annotations
    WHERE origin = 'ml' AND status = 'pending' AND confidence > 0.85
    ORDER BY confidence DESC
""").fetchall()
```

---

## 5. Deuda técnica y limitaciones conocidas

### 5.1 Renderización de máscara como polígono (gap principal)

**Descripción:** el flujo de inferencia ML cierra exitosamente hasta el punto en que el plugin recibe la máscara binaria y el score desde el backend. El siguiente paso — convertir esa máscara en un polígono vectorial editable dentro de la capa de anotaciones de QGIS — no está integrado en la interfaz.

**Qué existe:** el archivo `mask_to_polygon.py` implementa la conversión de máscara binaria a polígono usando `rasterio` y `shapely`. Funciona correctamente de forma aislada y está cubierto por tests. Lo que falta es integrarlo en el callback de `SamWorker.finished` dentro de `geoglyph.py`, crear la geometría como `QgsFeature` y agregarla a la capa de anotaciones.

**Estimación de esfuerzo:** 1 sprint (2 semanas). El código de conversión ya existe; el trabajo es la integración en el hilo de QGIS y el manejo de la reproyección de coordenadas (la máscara está en píxeles del ROI, hay que convertirla a coordenadas del CRS del proyecto).

**Archivos relevantes:** `mask_to_polygon.py`, `sam_client.py` (señal `finished`), `geoglyph.py` (método que recibe la señal), `annotation_manager.py`.

---

### 5.2 Exportación de capas realzadas es lenta

**Descripción:** guardar una capa generada por Color Ramp o DStretch en formato GeoTIFF puede tardar varios minutos si el archivo original es grande. Esta funcionalidad fue excluida del video demo por esta razón.

**Causa probable:** la capa realzada se construye en memoria como un array NumPy y se escribe en disco mediante `rasterio` sin streaming ni compresión progresiva. Para archivos de varios GB esto es ineficiente.

**Posible solución:** usar el modo de escritura por bloques (*tiled writing*) de `rasterio` y aplicar compresión `DEFLATE` o `LZW` al escribir el GeoTIFF.

---

### 5.3 `infer_worker.py` es código legado

**Descripción:** `infer_worker.py` implementa un worker de inferencia basado en `urllib` que envía el bbox como JSON (sin imagen). Corresponde a la integración con el backend mock de una etapa anterior del proyecto. El worker real y funcional es `sam_client.py`.

**Impacto:** ninguno en producción (no se llama desde el flujo principal). Agrega confusión para un desarrollador nuevo y tiene tests que cubren comportamiento que ya no existe en el backend.

**Recomendación:** eliminar `infer_worker.py` y sus tests en el próximo sprint de limpieza.

---

### 5.4 Job `release` del pipeline CI no implementado

**Descripción:** el documento de diseño describe un job `release` que crearía un GitHub Release público con el `.zip` del plugin al hacer push de un tag `vX.Y.Z`. Este job no está en el pipeline actual.

**Impacto:** los artefactos del pipeline (el `.zip` instalable) solo son accesibles desde GitHub Actions con cuenta autenticada, y caducan a los 90 días. Para distribuirlo a investigadores y estudiantes sin cuenta de GitHub, hay que crear el release manualmente.

**Esfuerzo estimado:** 2–3 horas. El workflow de GitHub Actions necesita un job adicional con `actions/create-release` y `actions/upload-release-asset`, condicionado a `if: startsWith(github.ref, 'refs/tags/v')`.

---

### 5.5 El campo `user` en `sessions` no está implementado

**Descripción:** la tabla `sessions` tiene un campo `user` reservado para identificar quién realizó la sesión, pero el plugin nunca lo escribe. Siempre queda NULL.

**Impacto:** no afecta el funcionamiento. Afecta la capacidad de generar métricas de uso por usuario, que era un requisito de CENIA.

---

### 5.6 Comentarios desactualizados en el backend

**Descripción:** al migrar de MobileSAM a SAM 2, algunos comentarios en `main.py` (líneas 37 y 108) quedaron con referencias a "MobileSAM". El comportamiento es correcto; solo los comentarios son imprecisos.

---

## 6. Cómo extender o reemplazar el modelo

Si en el futuro se quiere usar un modelo diferente (otra variante de SAM 2, un modelo fine-tuneado en geoglifos, u otro modelo de segmentación), los únicos archivos que hay que modificar son:

### `backend/sam_wrapper.py`

Este archivo es el único punto de contacto entre el backend y el modelo. Expone dos funciones:

```python
def initialize_sam() -> None:
    """Carga el modelo una sola vez al arrancar el servidor."""

def run_sam(
    image: np.ndarray,          # imagen RGB (H, W, 3) uint8
    points: Optional[np.ndarray],  # puntos de prompt (N, 2) en píxeles
    labels: Optional[np.ndarray],  # labels asociados (N,) con 1=fg, 0=bg
) -> Tuple[np.ndarray, float]:
    """Retorna (máscara_binaria, score_confianza).
    
    La máscara es un array (H, W) uint8 con valores 0 o 255.
    El score es un float en [0, 1].
    """
```

Para reemplazar el modelo, basta con reimplementar estas dos funciones manteniendo la misma firma. El resto del backend (`main.py`) no necesita cambios.

### `backend/requirements.txt`

Agregar o reemplazar la dependencia del modelo. Actualmente:

```
sam-2 @ git+https://github.com/facebookresearch/sam2.git
torch>=2.4.0
torchvision>=0.19.0
```

### Nada más

El plugin (`sam_client.py`) no sabe nada sobre el modelo. Solo envía una imagen PNG y espera recibir una máscara PNG en base64 con un score. El contrato del endpoint `/infer` no cambia.

---

## 7. Mapa de archivos clave

```
/
├── geoglyph.py               # Punto de entrada del plugin; conecta UI con lógica
├── geoglyph_panel.py         # Panel lateral principal (3 pestañas)
├── sam_client.py             # Worker HTTP que llama a POST /infer (SAM 2)
├── infer_worker.py           # Worker HTTP legado (urllib, mock); candidato a eliminar
├── health_worker.py          # Polling periódico a GET /health
├── mask_to_polygon.py        # Conversión máscara binaria → polígono (listo, no integrado)
├── annotation_manager.py     # Persistencia: lee/escribe en el GeoPackage
├── annotation_state.py       # Estado en memoria de las anotaciones activas
├── annotation_tool.py        # Herramienta de dibujo manual en el canvas de QGIS
├── roi_select_tool.py        # Herramienta de selección rectangular del ROI
├── raster_crop.py            # Extracción de píxeles RGB del ROI desde la capa ráster
├── color_ramp_worker.py      # Worker asíncrono para Color Ramp
├── dstretch_worker.py        # Worker asíncrono para DStretch
├── decorrelation_stretch.py  # Algoritmo de decorrelación (núcleo matemático)
├── split_view_manager.py     # Lógica de la vista side-by-side
├── annotations_style.qml     # Estilos de color por estado (QML de QGIS)
│
├── backend/
│   ├── main.py               # Servidor FastAPI con endpoints /health /info /enhance /infer
│   └── sam_wrapper.py        # Wrapper de SAM 2 (el único archivo a cambiar para otro modelo)
│
├── scripts/
│   └── init_gpkg.py          # Script CLI para crear el GeoPackage con su esquema
│
├── tests/                    # Suite de tests (pytest)
│   ├── conftest.py           # Fixtures y markers (qgis / no-qgis)
│   ├── test_infer_endpoint.py
│   ├── test_mask_to_polygon.py
│   ├── test_annotation_state.py
│   ├── test_annotation_persistence.py
│   ├── test_annotation_notes.py
│   └── ...
│
├── requirements.txt          # Dependencias del plugin
├── backend/requirements.txt  # Dependencias del backend (SAM 2, PyTorch, FastAPI)
├── ruff.toml                 # Configuración del linter
└── .github/workflows/ci.yml  # Pipeline CI (lint → test → test-qgis → build)
```

---

## 8. Contactos y accesos

| Recurso | Acceso |
|---------|--------|
| Repositorio GitHub | https://github.com/JaviL13/Taller-de-Integracion-G09 |
| Tablero Jira | https://taller-integracion-g05.atlassian.net/jira/software/projects/TIGS/boards/34 (solicitar acceso a javipaz.larrain@uc.cl) |
| OneDrive (entregables y minutas) | Solicitar acceso al equipo |
| Imágenes arqueológicas reales | Coordinarse con EAA_UC — estas imágenes no están en el repositorio por razones de patrimonio cultural |
| Clúster IALab (CENIA) | Coordinarse con CENIA para desplegar el backend con GPU |

### Equipo de desarrollo (Grupo 09)

- Ana Villar
- Fernanda Godoy
- Amada Saez
- Antonia Riffo
- Javiera Larraín

**Product Owner CENIA:** Francisca Gil

---

*Documento generado al cierre del proyecto — Junio 2026*
