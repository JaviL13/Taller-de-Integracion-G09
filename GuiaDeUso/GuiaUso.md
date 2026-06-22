# GeoGlyph — Manual de Uso

> Plataforma de Anotación Asistida para Geoglifos  
> Proyecto de Título DCC — CENIA / EAA_UC  
> Versión: 1.0 | Junio 2026

---

## Tabla de Contenidos

1. [Descripción general](#1-descripción-general)
2. [Panel lateral de GeoGlyph](#2-panel-lateral-de-geoglyph)
3. [Pestaña Principal](#3-pestaña-principal)
   - 3.1 [Cargar imagen](#31-cargar-imagen)
   - 3.2 [Realce visual](#32-realce-visual)
   - 3.3 [Vista Side-by-Side](#33-vista-side-by-side)
   - 3.4 [Inferencia ML](#34-inferencia-ml)
4. [Pestaña Anotaciones](#4-pestaña-anotaciones)
   - 4.1 [Dibujar polígono](#41-dibujar-polígono)
   - 4.2 [Seleccionar ROI (rect)](#42-seleccionar-roi-rect)
   - 4.3 [Importar anotaciones](#43-importar-anotaciones)
   - 4.4 [Exportar anotaciones](#44-exportar-anotaciones)
   - 4.5 [Exportar Capa Realzada](#45-exportar-capa-realzada)
   - 4.6 [Estado de anotación](#46-estado-de-anotación)
   - 4.7 [Historial de notas](#47-historial-de-notas)
5. [Pestaña Polígonos](#5-pestaña-polígonos)

---

## 1. Descripción general

**GeoGlyph** es un plugin para QGIS que asiste a investigadores y arqueólogos en la identificación y anotación de geoglifos en imágenes aéreas de alta resolución. El plugin se integra directamente en el entorno de trabajo habitual de QGIS, extendiendo sus capacidades con herramientas especializadas para el análisis arqueológico.

Las funcionalidades principales son:

- Carga y visualización de imágenes geoespaciales en formato GeoTIFF.
- Realce visual de imágenes mediante técnicas arqueológicas (Color Ramp y Decorrelation Stretch).
- Comparación simultánea de dos configuraciones de realce mediante vista Side-by-Side.
- Creación de anotaciones manuales mediante polígonos sobre el mapa.
- Segmentación asistida por inteligencia artificial mediante el modelo SAM.
- Gestión del ciclo de vida de las anotaciones: pendiente, aprobada y rechazada.
- Registro de notas asociadas a cada anotación con historial completo.
- Exportación de anotaciones aprobadas en formato GeoJSON.

---

## 2. Panel lateral de GeoGlyph

Al activar el plugin desde el menú **Ráster → GeoGlyph**, se despliega un panel lateral a la derecha de la pantalla de QGIS. Este panel es el punto de entrada para todas las funcionalidades del plugin y está organizado en tres pestañas:

- **Principal:** contiene las herramientas de carga de imagen, realce visual e inferencia ML.
- **Anotaciones:** contiene todas las herramientas de creación, gestión y validación de anotaciones.
- **Polígonos:** muestra el listado completo de anotaciones creadas con opciones de filtrado.

El panel es acoplable: se puede mover, redimensionar o flotar como ventana independiente según la preferencia del usuario.

---

## 3. Pestaña Principal

La pestaña **Principal** agrupa las herramientas de carga de imagen, realce visual e inferencia con el modelo SAM.

### 3.1 Cargar imagen

**Botón:** `Abrir GeoTIFF`

Para comenzar a trabajar, primero se debe cargar una imagen geoespacial en QGIS. Al hacer clic en **Abrir GeoTIFF**, se abre un explorador de archivos que permite seleccionar un archivo en formato `.tif` o `.tiff` desde el disco.

Una vez seleccionado, la imagen se incorpora automáticamente como una capa ráster en el proyecto de QGIS y queda visible en el mapa. El sistema de coordenadas de la imagen se respeta automáticamente.

> **Nota:** El plugin está optimizado para trabajar con ortomosaicos e imágenes de drones. Para archivos de gran tamaño (mayores a 500 MB) se recomienda hacer zoom a la zona de interés antes de aplicar realces.

### 3.2 Realce visual

La sección de **Realce visual** permite mejorar la visibilidad de patrones arqueológicos en la imagen cargada. Incluye dos técnicas de procesamiento de imágenes ampliamente utilizadas en arqueología.

**Menú desplegable "Tipo de realce":** permite seleccionar entre:
- **Color Ramp:** aplica una escala de colores sobre una banda específica de la imagen.
- **Decorrelation Stretch:** aplica un estiramiento de decorrelación (DStretch) sobre las bandas de la imagen para resaltar diferencias cromáticas sutiles.

Al cambiar el tipo de realce, las opciones disponibles debajo del menú se actualizan automáticamente para mostrar solo los parámetros relevantes para esa técnica.

**Botón:** `Aplicar Realce`

Ejecuta el realce seleccionado con los parámetros configurados. El resultado se agrega como una nueva capa en QGIS, preservando la imagen original sin modificarla.

#### Color Ramp

Color Ramp asigna una escala de colores a los valores numéricos de una banda del ráster. Es útil para visualizar variaciones de elevación, humedad u otras variables que no son evidentes en la representación original en escala de grises.

**Parámetros disponibles:**

- **Banda:** menú desplegable que permite seleccionar qué banda de la imagen se va a procesar. El número de opciones depende de las bandas que tenga la imagen cargada (por ejemplo, una imagen RGB tendrá las bandas 1, 2 y 3).

- **Aplicar sobre:** menú desplegable con dos opciones:
  - *Vista actual:* procesa únicamente la región visible en el mapa en ese momento. Es más rápido y se recomienda para exploración.
  - *Imagen completa:* procesa toda la imagen. Puede tardar varios minutos en archivos grandes.

- **Esquema de color:** menú desplegable con dos opciones:
  - *Viridis:* escala de colores secuencial que va de morado oscuro (valores bajos) a amarillo (valores altos). Es adecuada para representar gradientes continuos y es perceptualmente uniforme.
  - *RdYlGn:* escala divergente tipo semáforo que va de rojo (valores bajos) a amarillo (valores medios) a verde (valores altos). Es útil para identificar zonas de interés diferenciadas.

- **Estiramiento de contraste (Min/Max):** dos campos de texto que permiten definir manualmente los valores mínimo y máximo del rango de color. Si se dejan en blanco (valor *Auto*), el sistema calcula automáticamente los valores a partir de las estadísticas de la imagen.

#### Decorrelation Stretch

Decorrelation Stretch (DStretch) es una técnica de procesamiento de imágenes que amplifica las diferencias cromáticas entre bandas aplicando un Análisis de Componentes Principales (PCA). El resultado revela variaciones de color que no son visibles a simple vista, lo que la hace especialmente útil para identificar geoglifos en terrenos áridos donde el contraste con el entorno es muy sutil.

Al seleccionar **Decorrelation Stretch** en el menú de tipo de realce y hacer clic en **Aplicar Realce**, se abre un panel movible con las siguientes secciones:

**Capa raster de entrada**

Permite elegir la imagen sobre la que se aplicará el realce. El menú desplegable muestra todas las capas ráster cargadas en el proyecto. Si la imagen no está cargada aún, el botón **… o abrir GeoTIFF desde disco** permite seleccionarla directamente desde el explorador de archivos.

**Bandas de entrada para el PCA**

Tres menús desplegables (**Canal 1**, **Canal 2**, **Canal 3**) permiten elegir qué bandas de la imagen alimentan el algoritmo PCA. Por defecto se asignan las tres primeras bandas disponibles. Elegir bandas repetidas produce un PCA degenerado; el sistema lo avisa y pide confirmación antes de continuar.

**Región a procesar**

Menú desplegable con dos opciones:
- *Vista actual del mapa (rápido):* procesa únicamente la región visible en el mapa en ese momento. Recomendado para exploración iterativa.
- *Raster completo (procesamiento por tiles):* procesa toda la imagen dividiéndola en teselas para mantener el uso de memoria acotado. Adecuado para ortomosaicos grandes.

Debajo del menú se muestra el tamaño estimado de la región en píxeles y el modo de procesamiento que se utilizará (memoria directa o por teselas).

**Parámetros**

- **Saturación (%):** porcentaje de recorte por percentil aplicado al estiramiento final de color. Valores típicos entre 0,5 y 2,0. Un valor de 0 desactiva el recorte. Por defecto: 1,0 %.

**Reducción de ruido**

Controles opcionales para mitigar el ruido de color ("rainbow noise") que puede aparecer en zonas de baja varianza:

- **Suavizado PCA:** regularización aplicada al PCA para limitar la amplificación de los ejes con poca varianza, que es donde se concentra el ruido del sensor. El valor se expresa en porcentaje (0–5 %). Un valor de 0 aplica el DStretch canónico sin regularización. Por defecto: 1,0 %.
- **Filtro bilateral:** filtro post-procesamiento que suaviza zonas planas conservando los bordes de los geoglifos. Las opciones son *Desactivado*, *Suave*, *Medio* y *Fuerte*, correspondientes a kernels de tamaño creciente. Por defecto: Desactivado.

**Archivo de salida**

Campo de texto para definir la ruta del archivo GeoTIFF resultante. Si se deja vacío, se genera automáticamente un archivo temporal. El botón **…** abre un explorador de archivos para elegir la ubicación.

**Botón Aplicar**

Lanza el procesamiento en segundo plano. La barra de progreso indica el avance: en modo tiled muestra el porcentaje por teselas completadas; en modo memoria permanece en modo pulsante hasta que termina. La interfaz de QGIS permanece usable durante todo el proceso. Al finalizar, la capa resultante se agrega automáticamente al proyecto con el nombre `<imagen>_dstretch_<banda1><banda2><banda3>`.

> **Nota:** Para imágenes grandes se recomienda usar primero la opción *Vista actual del mapa* para ajustar los parámetros, y luego aplicar sobre el *Raster completo* una vez encontrada la configuración adecuada.

### 3.3 Vista Side-by-Side

**Botón:** `Activar Vista Side-by-Side`  
**Botón:** `Sincronización: ON / OFF`

La vista Side-by-Side permite comparar dos configuraciones de realce visual simultáneamente, mostrando dos mapas al mismo tiempo. Es útil para decidir qué técnica de realce ayuda mejor a identificar los geoglifos en una imagen determinada.

**Cómo usar la vista Side-by-Side:**

1. Cargar una imagen GeoTIFF y aplicar un primer realce en la vista principal.
2. Hacer clic en **Activar Vista Side-by-Side**. Aparecerá un segundo panel de mapa en la parte inferior de la ventana de QGIS mostrando las mismas capas.
3. Aplicar un realce distinto desde el panel de GeoGlyph. El nuevo realce se agrega como capa y es visible en ambas vistas.
4. Comparar ambas vistas navegando el mapa.
5. Para volver a la vista normal, hacer clic en **Desactivar Vista Side-by-Side**.

**Sincronización de zoom y pan:**

Cuando la sincronización está activa (**Sincronización: ON**), cualquier movimiento o zoom en el mapa principal se replica automáticamente en la vista secundaria, permitiendo comparar la misma zona con distintos realces. Al hacer clic en el botón, la sincronización se desactiva (**Sincronización: OFF**) y cada vista se puede navegar de forma independiente.

> **Nota:** El botón de sincronización solo está habilitado cuando la Vista Side-by-Side está activa. El panel secundario es acoplable: se puede mover a cualquier lado de la ventana de QGIS o flotarlo como ventana independiente.

### 3.4 Inferencia ML

**Botón:** `Ejecutar SAM`

Ejecuta el modelo de segmentación SAM sobre el ROI previamente seleccionado en la pestaña **Anotaciones**. Este botón se habilita automáticamente después de seleccionar un ROI rectangular con la herramienta **Seleccionar ROI (rect)**.

El resultado de la inferencia se guarda automáticamente como una anotación con origen **ml-annotation** y estado **pending**, y aparece en el mapa para su revisión.

> **Nota:** Requiere que el backend de inferencia esté activo. Si no está disponible, el plugin muestra un aviso pero continúa funcionando con todas las demás herramientas sin interrupciones.

> **Nota:** Se recomienda hacer algún realce de imagen para mejorar la calidad de la recomendación.

---

## 4. Pestaña Anotaciones

La pestaña **Anotaciones** agrupa todas las herramientas para crear, gestionar y validar anotaciones sobre la imagen geoespacial.

### 4.1 Dibujar polígono

**Botón:** `Dibujar polígono`

Activa la herramienta de dibujo manual de polígonos sobre el mapa. Permite trazar el contorno de un geoglifo o cualquier estructura de interés directamente sobre la imagen.

**Controles:**
- **Clic izquierdo:** agrega un vértice al polígono en la posición del cursor.
- **Clic derecho:** cierra el polígono y guarda la anotación. Se requiere un mínimo de 3 vértices.
- **Tecla Escape:** cancela el dibujo en curso sin guardar nada.

Una vez cerrado el polígono, la anotación se guarda automáticamente en el GeoPackage local con estado **pending** y origen **human**. El polígono aparece en color amarillo sobre el mapa.

### 4.2 Seleccionar ROI (rect)

**Botón:** `Seleccionar ROI (rect)`

Activa la herramienta de selección de una Región de Interés (ROI) rectangular sobre el mapa. Es el primer paso para ejecutar la segmentación asistida con el modelo SAM.

**Cómo usarlo:**
1. Hacer clic en **Seleccionar ROI (rect)**.
2. Mantener presionado el clic izquierdo y arrastrar sobre el mapa para definir el rectángulo de interés alrededor del geoglifo.
3. Al soltar el clic, el ROI queda definido y se habilita automáticamente el botón **Ejecutar SAM** en la sección de Inferencia ML de la pestaña Principal.
4. Ir a la pestaña **Principal** y hacer clic en **Ejecutar SAM** para obtener la máscara de segmentación.

> **Nota:** Esta funcionalidad requiere que el backend de inferencia esté activo. Si el backend no está disponible, el plugin mostrará un aviso pero continuará funcionando con todas las demás herramientas sin interrupciones.

### 4.3 Importar anotaciones

**Botón:** `Importar anotaciones`

Permite importar anotaciones existentes en formato GeoJSON al proyecto actual. Las anotaciones importadas se agregan a la capa de anotaciones con su estado y origen originales preservados.

### 4.4 Exportar anotaciones

**Botón:** `Exportar anotaciones`

Exporta **todas** las anotaciones (aprobadas, rechazadas y pendientes) a un archivo GeoJSON. Al hacer clic, se abre un explorador de archivos para seleccionar la ubicación y nombre del archivo de salida.

El archivo exportado incluye para cada anotación: la geometría georreferenciada, el origen (human o ml-annotation), las notas asociadas, el score de confianza (si aplica) y la fecha y hora del último cambio.

### 4.5 Exportar Capa Realzada

**Botón:** `Exportar Capa Realzada`

Exporta la capa ráster actualmente seleccionada en el panel de capas de QGIS como un nuevo archivo GeoTIFF. Es útil para guardar el resultado de un realce visual aplicado para su uso posterior en otras herramientas.

Al hacer clic, se abre un explorador de archivos para definir la ruta y nombre del archivo de salida. La capa exportada conserva la georreferenciación original.

> **Advertencia:** Para imágenes de gran tamaño, este proceso puede tardar varios minutos. Se recomienda exportar solo la vista actual aplicando el realce sobre la región visible en lugar de la imagen completa.

### 4.6 Estado de anotación

Esta sección muestra información sobre las anotaciones seleccionadas en el mapa y permite gestionar su ciclo de vida.

- **Selección actual:** indica cuántas anotaciones están seleccionadas en el mapa en ese momento. Los botones de Aprobar, Rechazar y Pendiente solo se habilitan cuando hay al menos una anotación seleccionada.
- **Confianza:** muestra el score de confianza del modelo SAM para la anotación seleccionada (entre 0 y 1). Solo aplica para anotaciones de origen ml-annotation. Para anotaciones manuales aparece como —.

**Botón:** `Aprobar`  
**Botón:** `Rechazar`  
**Botón:** `Pendiente`

Estos botones permiten cambiar el estado de las anotaciones seleccionadas en el mapa. Se pueden seleccionar múltiples anotaciones a la vez para cambiarles el estado en bloque.

Los tres estados posibles son:

- **Pending (naranja):** estado inicial de toda anotación recién creada o importada. Indica que aún no ha sido revisada por el arqueólogo.
- **Approved (verde):** la anotación fue revisada y validada por el arqueólogo.
- **Rejected (rojo):** la anotación fue descartada. Se conserva en el GeoPackage para mantener la trazabilidad.

Los colores se aplican automáticamente sobre los polígonos en el mapa al cambiar el estado.

### 4.7 Historial de notas

**Campo de texto:** `Agregar nota ...`  
**Botón:** `Agregar nota`

Permite asociar notas de texto a una anotación seleccionada. Cada nota que se agrega se registra con su fecha y hora, el estado de la anotación en ese momento, el origen y el score de confianza. Las notas anteriores no se borran, por lo que se construye un historial completo de observaciones.

**Cómo agregar una nota:**
1. Seleccionar una anotación en el mapa.
2. Escribir el texto en el campo **Agregar nota ...**.
3. Hacer clic en **Agregar nota**. La nota aparecerá en la tabla de historial y el campo de texto se limpiará automáticamente.

**Tabla de historial:** muestra todas las notas registradas para la anotación seleccionada, ordenadas cronológicamente. Las columnas son:

| Columna | Descripción |
|---|---|
| Fecha | Fecha y hora en que se registró la nota |
| Nota | Texto de la observación ingresada |
| Estado | Estado de la anotación en el momento de registrar la nota |
| Origen | Origen de la anotación (human o ml-annotation) |
| Score | Score de confianza del modelo (solo para anotaciones de origen ml) |

> **Nota:** Si se seleccionan múltiples anotaciones, el historial de notas se oculta y el campo de texto se limpia. Para ver el historial es necesario tener exactamente una anotación seleccionada.

---

## 5. Pestaña Polígonos

La pestaña **Polígonos** ofrece una vista centralizada de todas las anotaciones del proyecto en formato de tabla, permitiendo explorarlas y gestionarlas sin tener que buscarlas manualmente en el mapa.

**Menú desplegable "Filtrar por estado":** permite mostrar solo las anotaciones en un estado específico. Las opciones son:
- **All:** muestra todas las anotaciones sin filtrar.
- **Approved:** muestra solo las anotaciones aprobadas.
- **Rejected:** muestra solo las anotaciones rechazadas.
- **Pending:** muestra solo las anotaciones pendientes.

**Tabla de polígonos:** muestra una fila por cada anotación con las siguientes columnas:

| Columna | Descripción |
|---|---|
| Estado | Estado actual de la anotación (pending, approved o rejected) |
| Origen | Cómo fue creada la anotación (human o ml-annotation) |
| Score | Score de confianza del modelo (solo para anotaciones de origen ml) |

**Interacción con el mapa:** al hacer clic en cualquier fila de la tabla, el mapa se centra automáticamente en el polígono correspondiente y lo selecciona en la capa de anotaciones. Esto facilita la revisión sistemática de todas las anotaciones sin necesidad de buscarlas manualmente en la imagen.

---

*Documento generado como parte del Sprint 6*  
*Proyecto GeoGlyph — Taller de Integración, DCC PUC — Junio 2026*
