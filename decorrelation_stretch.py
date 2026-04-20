# coding: utf-8 
#Decorrelation Stretch (DStretch) vía PCA para GeoGlyph.

#Técnica clásica de realce arqueológico (Gillespie et al., 1986) que aumenta el
# contraste de color en imágenes con bandas altamente correlacionadas — típico en
# ortofotos de desiertos donde los geoglifos tienen diferencias cromáticas sutiles.

#Procedimiento:
  #1. Se toman 3 bandas RGB del GeoTIFF de entrada.
  #2. Se calcula media μ y matriz de covarianza Σ sobre los píxeles válidos.
  #3. Se descompone Σ = V · Λ · Vᵀ (autovectores/autovalores).
  #4. Se construye una matriz de estiramiento M = V · diag(k/√λᵢ) · Vᵀ que 
  # amplifica cada eje principal hasta una desviación común k.
  #5. Se aplica X' = (X − μ) · M + μ, se recorta por percentil y se escala a 8 bits.
  #6. Se escribe un nuevo GeoTIFF preservando geotransform, CRS y proyección.

#Solo depende de numpy y osgeo.gdal, ambos disponibles en QGIS por defecto.

from __future__ import annotations

import time
from typing import Dict, Iterable, Optional, Tuple

import numpy as np

# Nota: el import de osgeo se hace diferido dentro de decorrelation_stretch()
# para que el módulo se pueda importar (y testear) sin tener GDAL instalado.


def _fit_stretch_params(
    X_sample: np.ndarray,
    saturation_pct: float,
    regularization: float = 0.0,
) -> Dict[str, np.ndarray]:
    """A partir de una muestra de píxeles válidos (N, 3), estima los parámetros
    fijos de la transformación: media μ, matriz M, y bandas de percentil
    (low, high) que definen el estiramiento final a [0, 255].

    Todos los píxeles del raster — vistos en memoria completa o por tiles —
    se pueden luego transformar de manera consistente con estos parámetros
    (ver `_apply_stretch_params`).

    Parameters
    ----------
    X_sample : ndarray (N, 3)
        Muestra de píxeles válidos (por ejemplo, tomados de un thumbnail).
    saturation_pct : float
        Porcentaje de saturación para los percentiles finales.
    regularization : float en [0, 1]
        "Piso de ruido" relativo al autovalor más grande. Por qué existe:
        el estiramiento canónico multiplica cada eje por k/√λ. Cuando λ es
        muy chico (ejes de poca varianza, que típicamente corresponden a
        ruido de sensor + señal arqueológica tenue), ese factor puede pasar
        fácilmente de 20×. Eso amplifica muchísimo el ruido y genera los
        "píxeles de colores" en zonas uniformes.
        Con regularization > 0, calculamos en su lugar k/√(λ + ε) donde
        ε = regularization × λ_max. Para ejes grandes (λ ≈ λ_max) ε es
        despreciable y el realce ni se entera. Para ejes chicos (λ ≪ λ_max)
        ε domina y la amplificación queda topada en ~k/√ε.
        Valores típicos: 0.005–0.05 (0.5 %–5 %). Default 0 → comportamiento
        idéntico al dstretch original.
    """
    if X_sample.ndim != 2 or X_sample.shape[-1] != 3:
        raise ValueError("X_sample debe tener forma (N, 3).")
    if X_sample.shape[0] < 16:
        raise RuntimeError(
            "Muy pocos pixeles válidos para estimar la estadística de la imagen."
        )
    if regularization < 0.0 or regularization > 1.0:
        raise ValueError("regularization debe estar entre 0 y 1.")

    X_sample = X_sample.astype(np.float32, copy=False)
    mu = X_sample.mean(axis=0)
    cov = np.cov(X_sample - mu, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)

    # Piso numérico duro — evita dividir por cero en casos patológicos.
    eigvals = np.maximum(eigvals, 1e-12)

    # Regularización Tikhonov-like: sumamos ε a los autovalores antes de
    # invertir √λ. Esta operación deja μ y los autovectores intactos, así
    # que la "dirección" del estiramiento no cambia — solo su magnitud en
    # los ejes pequeños, que es justo donde vive el ruido.
    if regularization > 0:
        eps = float(regularization) * float(eigvals.max())
        eigvals_effective = eigvals + eps
    else:
        eigvals_effective = eigvals

    # k es la desviación estándar objetivo para cada eje del output.
    # Usamos los eigvals regularizados para mantener consistencia con la
    # inversión de abajo — si no, k sería demasiado grande para los ejes
    # chicos regularizados y el clip a 0..255 saturaría raro.
    k = float(np.sqrt(eigvals_effective).mean())
    D = np.diag(k / np.sqrt(eigvals_effective))
    M = (eigvecs @ D @ eigvecs.T).astype(np.float32)

    # Percentiles calculados sobre la muestra ya transformada. Como la muestra
    # es estadísticamente representativa del raster completo, los percentiles
    # globales se estiman correctamente desde aquí.
    X_sample_out = (X_sample - mu) @ M + mu
    if saturation_pct > 0:
        low = np.percentile(X_sample_out, saturation_pct, axis=0).astype(np.float32)
        high = np.percentile(
            X_sample_out, 100.0 - saturation_pct, axis=0
        ).astype(np.float32)
    else:
        low = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        high = np.array([255.0, 255.0, 255.0], dtype=np.float32)

    return {
        "mu": mu.astype(np.float32),
        "M": M,
        "eigvals": eigvals.astype(np.float32),
        "eigvecs": eigvecs.astype(np.float32),
        "target_std": np.float32(k),
        "low": low,
        "high": high,
        "regularization": np.float32(regularization),
    }


def _apply_stretch_params(
    img: np.ndarray,
    params: Dict[str, np.ndarray],
    nodata_mask: Optional[np.ndarray] = None,
    saturation_pct: float = 1.0,
) -> np.ndarray:
    """Aplica una transformación ya ajustada (μ, M, low, high) a una tesela
    (H, W, 3) y devuelve uint8 (H, W, 3). Pensada para procesamiento por tiles
    — la transformación es afín, así que es idéntica cualquiera sea el tamaño
    del bloque; la consistencia entre tiles viene dada por usar los mismos
    parámetros globales."""
    if img.ndim != 3 or img.shape[-1] != 3:
        raise ValueError("img debe tener forma (H, W, 3).")

    height, width, _ = img.shape
    X = img.astype(np.float32, copy=False).reshape(-1, 3)

    mu = params["mu"]
    M = params["M"]
    low = params["low"]
    high = params["high"]

    X_out = (X - mu) @ M + mu
    if saturation_pct > 0:
        scale = np.where((high - low) > 1e-6, high - low, 1.0)
        X_out = (X_out - low) / scale * 255.0
    X_out = np.clip(X_out, 0, 255)

    out = X_out.reshape(height, width, 3).astype(np.uint8)
    if nodata_mask is not None and nodata_mask.any():
        out[nodata_mask] = 0
    return out


def _decorrelation_stretch_array(
    img: np.ndarray,
    nodata_mask: Optional[np.ndarray] = None,
    saturation_pct: float = 1.0,
    sample_limit: int = 1_000_000,
    regularization: float = 0.0,
) -> Tuple[np.ndarray, Dict[str, object]]:
    """Núcleo matemático puro (sin I/O). Recibe un ndarray (H, W, 3) float
    y devuelve el resultado como uint8 (H, W, 3) junto con estadísticas.

    Separado de la función principal para poder testearlo sin GDAL.
    Implementado sobre `_fit_stretch_params` + `_apply_stretch_params` para
    reusar la misma matemática en el camino tiled (rasters grandes).
    """
    if img.ndim != 3 or img.shape[-1] != 3:
        raise ValueError("Se esperaba un ndarray de forma (H, W, 3).")

    height, width, _ = img.shape

    if nodata_mask is None:
        nodata_mask = np.zeros((height, width), dtype=bool)
    # También descartamos pixeles todo-cero (bordes de vuelo)
    nodata_mask = nodata_mask | np.all(img == 0, axis=-1)

    X = img.astype(np.float32, copy=False).reshape(-1, 3)
    valid_flat = ~nodata_mask.reshape(-1)
    X_valid = X[valid_flat]

    if X_valid.shape[0] > sample_limit:
        rng = np.random.default_rng(42)
        idx = rng.choice(X_valid.shape[0], size=sample_limit, replace=False)
        X_sample = X_valid[idx]
    else:
        X_sample = X_valid

    params = _fit_stretch_params(
        X_sample,
        saturation_pct=saturation_pct,
        regularization=regularization,
    )
    out = _apply_stretch_params(
        img, params, nodata_mask=nodata_mask, saturation_pct=saturation_pct
    )

    stats = {
        "mean": params["mu"].tolist(),
        "eigenvalues": params["eigvals"].tolist(),
        "eigenvectors": params["eigvecs"].tolist(),
        "target_std": float(params["target_std"]),
        "low": params["low"].tolist(),
        "high": params["high"].tolist(),
        "regularization": float(params["regularization"]),
    }
    return out, stats


def _bilateral_filter_numpy(
    img_uint8: np.ndarray,
    d: int,
    sigma_color: float,
    sigma_space: float,
) -> np.ndarray:
    """Implementación del filtro bilateral en numpy puro.

    Fallback cuando cv2 no está disponible (común en el Python empaquetado
    de QGIS, donde instalar opencv-python no siempre es trivial). Es más
    lenta que cv2 pero no requiere dependencias extra — sólo numpy, que ya
    tenemos sí o sí.

    Fórmula: para cada píxel p con valor I(p), el output es
        O(p) = (Σ_q w_s(p,q) · w_r(I(p), I(q)) · I(q)) / Σ_q w_s · w_r
    donde q itera sobre los vecinos en un cuadrado de lado d, y:
      - w_s(p,q) = exp(-||p-q||² / 2σ_space²)   (peso espacial)
      - w_r(a,b) = exp(-||a-b||² / 2σ_color²)   (peso de rango/valor)

    La implementación es vectorizada: en vez de iterar píxel por píxel,
    iteramos por cada OFFSET (dy, dx) del kernel y operamos sobre arrays
    enteros desplazados. Son d² iteraciones sobre arrays (H,W,3) — para
    d=7 son 49 iteraciones, totalmente manejable para tiles de 1024×1024.
    """
    img = img_uint8.astype(np.float32)
    H, W, _ = img.shape
    radius = int(d) // 2

    # Pre-cómputo del kernel espacial: una gaussiana 2D fija del tamaño del
    # kernel. No depende de la imagen, así que lo calculamos una sola vez.
    offsets = np.arange(-radius, radius + 1)
    dy, dx = np.meshgrid(offsets, offsets, indexing="ij")
    spatial_weights = np.exp(
        -(dx.astype(np.float32) ** 2 + dy.astype(np.float32) ** 2)
        / (2.0 * float(sigma_space) ** 2)
    )

    # Paddeamos con reflection para que los píxeles del borde no se "caigan"
    # hacia negro — si no, el filtro oscurecería la frontera de la imagen.
    padded = np.pad(
        img, ((radius, radius), (radius, radius), (0, 0)), mode="reflect"
    )

    # Acumuladores: numerador (Σ w · I_vecino) y denominador (Σ w).
    num = np.zeros_like(img)
    den = np.zeros((H, W, 1), dtype=np.float32)

    # Constante para el peso de rango, precalculada fuera del loop.
    two_sigma_color_sq = 2.0 * float(sigma_color) ** 2

    # Iteramos por cada (dy, dx) del kernel. En cada paso, `shifted` es la
    # imagen completa desplazada — es decir, el "vecino" de cada píxel en
    # esa dirección. Así el loop interno es O(H·W·3), no O(H·W·d²·3).
    for i in range(d):
        for j in range(d):
            shifted = padded[i : i + H, j : j + W, :]
            diff = shifted - img
            # Suma del cuadrado sobre los 3 canales → distancia de color
            # euclidiana al cuadrado; keepdims para que broadcast con la
            # imagen funcione sin problemas.
            range_weight = np.exp(
                -np.sum(diff * diff, axis=2, keepdims=True) / two_sigma_color_sq
            )
            w = spatial_weights[i, j] * range_weight
            num += shifted * w
            den += w

    # Normalización. El `maximum` evita división por cero en el caso
    # (teórico) de que todos los pesos sean 0.
    out = num / np.maximum(den, 1e-8)
    return np.clip(out, 0, 255).astype(np.uint8)


def _apply_bilateral_filter(
    img_uint8: np.ndarray,
    d: int,
    sigma_color: float,
    sigma_space: float,
) -> np.ndarray:
    """Suavizado edge-preserving post-dstretch. Pensado para eliminar el
    "speckle" de colores que aparece en zonas planas tras el estiramiento,
    sin borronear los contornos de los geoglifos.

    Intenta primero usar cv2.bilateralFilter (rápido, C++). Si cv2 no está
    disponible en el entorno (común en QGIS en macOS donde el Python
    empaquetado viene sin opencv-python), hace fallback a una implementación
    en numpy puro — funciona igual, solo que más lenta.

    Parameters
    ----------
    img_uint8 : ndarray (H, W, 3), uint8
    d : int
        Diámetro de la vecindad. Valores típicos: 5–9.
    sigma_color : float
        Cuánta diferencia de color toleramos antes de "cortar" el promedio.
        Mayor = más agresivo. Valores típicos: 15–40.
    sigma_space : float
        Cuánto influye la distancia espacial. Valores típicos: 5–10.
    """
    try:
        import cv2
        # cv2.bilateralFilter espera uint8 o float32; soporta multicanal.
        return cv2.bilateralFilter(
            img_uint8,
            d=int(d),
            sigmaColor=float(sigma_color),
            sigmaSpace=float(sigma_space),
        )
    except ImportError:
        # Fallback en numpy. Más lento pero sin dependencias extra.
        return _bilateral_filter_numpy(
            img_uint8, d=d, sigma_color=sigma_color, sigma_space=sigma_space
        )


def _read_thumbnail_sample(
    ds,
    band_indices: Tuple[int, int, int],
    xoff: int,
    yoff: int,
    xsize: int,
    ysize: int,
    sample_limit: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Lee una versión decimada (thumbnail) de la región pedida usando los
    parámetros buf_xsize/buf_ysize de GDAL, de modo que siempre cabe en
    memoria independientemente del tamaño del raster.

    GDAL hace el submuestreo en disco (lee solo los niveles de resolución
    que necesita), así que esto es barato incluso para ortofotos gigantes.

    Devuelve (img_thumbnail (H', W', 3) float32, nodata_mask (H', W') bool).
    El tamaño del thumbnail se elige para que tenga ~sample_limit píxeles.
    """
    total_px = xsize * ysize
    if total_px <= sample_limit:
        # La región entera cabe en la cuota de muestreo — leemos full-res.
        buf_w, buf_h = xsize, ysize
    else:
        scale = float(np.sqrt(total_px / sample_limit))
        buf_w = max(1, int(round(xsize / scale)))
        buf_h = max(1, int(round(ysize / scale)))

    channels = []
    nodata_masks = []
    for bi in band_indices:
        band = ds.GetRasterBand(bi)
        arr = band.ReadAsArray(
            xoff, yoff, xsize, ysize, buf_xsize=buf_w, buf_ysize=buf_h
        ).astype(np.float32, copy=False)
        nodata = band.GetNoDataValue()
        if nodata is not None:
            mask = arr == nodata
        else:
            mask = np.zeros_like(arr, dtype=bool)
        channels.append(arr)
        nodata_masks.append(mask)

    img = np.stack(channels, axis=-1)
    combined_mask = np.any(np.stack(nodata_masks, axis=-1), axis=-1)
    # Descartamos también los píxeles todo-cero (bordes de vuelo).
    combined_mask = combined_mask | np.all(img == 0, axis=-1)
    return img, combined_mask


def _process_tiled(
    ds,
    dst_ds,
    band_indices: Tuple[int, int, int],
    xoff: int,
    yoff: int,
    xsize: int,
    ysize: int,
    params: Dict[str, np.ndarray],
    saturation_pct: float,
    tile_size: int,
    bilateral_d: int = 0,
    bilateral_sigma_color: float = 25.0,
    bilateral_sigma_space: float = 7.0,
    progress_cb=None,
) -> int:
    """Itera la región (xoff, yoff, xsize, ysize) en teselas de tile_size×tile_size,
    lee cada tile, aplica la transformación ya ajustada (params) y, opcionalmente,
    un filtro bilateral; luego lo escribe al raster de salida.

    Memoria máx: ~tile_size² × 3 canales × 4 bytes (float32) + halo ≈ 15 MB.

    Manejo de halos (importante): si `bilateral_d > 0`, cada tile se lee con
    un margen extra de `bilateral_d` píxeles por lado, traídos del raster
    fuente. La transformación + el filtro se aplican al tile padded completo,
    y sólo el centro (el tile "real") se escribe. Así el filtro siempre ve
    el contexto correcto de los vecinos y no se producen costuras entre tiles.
    """
    in_bands = [ds.GetRasterBand(bi) for bi in band_indices]
    nodata_values = [b.GetNoDataValue() for b in in_bands]
    out_bands = [dst_ds.GetRasterBand(i + 1) for i in range(3)]

    # Tamaño total del raster fuente — para clampear el halo en los bordes.
    full_width = ds.RasterXSize
    full_height = ds.RasterYSize

    use_bilateral = bilateral_d > 0
    halo = int(bilateral_d) if use_bilateral else 0

    tiles_y = (ysize + tile_size - 1) // tile_size
    tiles_x = (xsize + tile_size - 1) // tile_size
    total_tiles = tiles_x * tiles_y
    done = 0

    for ty in range(tiles_y):
        y0 = ty * tile_size
        th = min(tile_size, ysize - y0)
        for tx in range(tiles_x):
            x0 = tx * tile_size
            tw = min(tile_size, xsize - x0)

            # Coordenadas del tile en el raster fuente (sin halo).
            src_x = xoff + x0
            src_y = yoff + y0

            # Cuánto halo podemos leer en cada lado — nos topamos con los
            # bordes del raster fuente, no con los de la ventana.
            left_halo = min(halo, src_x)
            top_halo = min(halo, src_y)
            right_halo = min(halo, full_width - (src_x + tw))
            bottom_halo = min(halo, full_height - (src_y + th))

            read_x = src_x - left_halo
            read_y = src_y - top_halo
            read_w = tw + left_halo + right_halo
            read_h = th + top_halo + bottom_halo

            # Lee las 3 bandas para el tile padded en coords del raster fuente
            channels = []
            masks = []
            for bi_idx, b in enumerate(in_bands):
                arr = b.ReadAsArray(read_x, read_y, read_w, read_h).astype(
                    np.float32, copy=False
                )
                nd = nodata_values[bi_idx]
                if nd is not None:
                    masks.append(arr == nd)
                else:
                    masks.append(np.zeros_like(arr, dtype=bool))
                channels.append(arr)

            img_padded = np.stack(channels, axis=-1)
            nodata_padded = np.any(np.stack(masks, axis=-1), axis=-1)
            nodata_padded = nodata_padded | np.all(img_padded == 0, axis=-1)

            # 1. Aplicar el estiramiento PCA a todo el tile padded.
            out_padded = _apply_stretch_params(
                img_padded,
                params,
                nodata_mask=nodata_padded,
                saturation_pct=saturation_pct,
            )

            # 2. Filtro bilateral opcional, también sobre el padded.
            # Se aplica antes de recortar el halo, así los píxeles del borde
            # del tile real ven contexto real (no padding con ceros).
            if use_bilateral:
                out_padded = _apply_bilateral_filter(
                    out_padded,
                    d=bilateral_d,
                    sigma_color=bilateral_sigma_color,
                    sigma_space=bilateral_sigma_space,
                )

            # 3. Recortar el halo y escribir sólo el centro (tile "real").
            out_tile = out_padded[
                top_halo : top_halo + th,
                left_halo : left_halo + tw,
                :,
            ]

            for i in range(3):
                out_bands[i].WriteArray(out_tile[..., i], x0, y0)

            done += 1
            if progress_cb is not None:
                progress_cb(done, total_tiles)

    return done


def decorrelation_stretch(
    src_path: str,
    dst_path: str,
    band_indices: Iterable[int] = (1, 2, 3),
    saturation_pct: float = 1.0,
    sample_limit: int = 1_000_000,
    window: Optional[Tuple[int, int, int, int]] = None,
    in_memory_limit: int = 16_000_000,
    tile_size: int = 1024,
    regularization: float = 0.0,
    bilateral_d: int = 0,
    bilateral_sigma_color: float = 25.0,
    bilateral_sigma_space: float = 7.0,
    progress_cb=None,
) -> Dict[str, object]:
    """Aplica decorrelation stretch sobre 3 bandas de un raster y escribe el resultado.

    Para regiones pequeñas, se usa el camino en memoria (rápido, simple).
    Para regiones grandes, se usa procesamiento por teselas en dos pasadas
    (igual que QGIS hace el render): pasada 1 lee un thumbnail decimado de
    toda la región para ajustar los parámetros (μ, M, percentiles), y
    pasada 2 itera el raster en tiles aplicando la transformación ya fija.
    Esto permite procesar ortofotos gigantes sin quedarse sin memoria.

    Parameters
    ----------
    src_path : str
        Ruta al GeoTIFF de entrada (o cualquier raster que GDAL pueda abrir).
    dst_path : str
        Ruta al GeoTIFF de salida (se sobreescribe si existe).
    band_indices : iterable de 3 enteros (1-indexados, convención GDAL)
        Bandas del raster fuente que conformarán los 3 canales de entrada al PCA.
    saturation_pct : float en [0, 10]
        Porcentaje de saturación para el estiramiento final por percentil.
        0 desactiva el recorte por percentil (se usa clip 0..255 directo).
    sample_limit : int
        Máximo de píxeles usados para ajustar la estadística (μ, Σ, percentiles).
        La transformación igual se aplica a todos los píxeles del raster.
    window : (xoff, yoff, xsize, ysize) o None
        Si se entrega, sólo se procesa la ventana indicada (en pixeles del
        raster fuente). Si es None se procesa el raster completo. La
        georreferenciación del output se ajusta automáticamente al offset.
    in_memory_limit : int
        Si la región a procesar tiene menos de este número de píxeles, se
        carga completa en memoria (camino rápido). Si es mayor, se usa
        procesamiento tiled en dos pasadas (memoria acotada a ~tile_size²).
        Default 16 Mpx (~4000×4000 px).
    tile_size : int
        Tamaño del tile (en píxeles por lado) para el camino tiled.
        Default 1024 → tiles de 1024×1024×3 float32 ≈ 12 MB.
    regularization : float en [0, 1]
        "Piso de ruido" en el PCA para reducir la amplificación de ruido
        en zonas uniformes. Ver `_fit_stretch_params` para el detalle
        matemático. Default 0 → dstretch canónico sin regularización.
    bilateral_d : int
        Diámetro del filtro bilateral post-procesamiento. 0 desactiva el
        filtro (default). Valores típicos para reducir "speckle":
        5 (suave), 7 (medio), 9 (fuerte).
    bilateral_sigma_color : float
        σ del término de color en el filtro bilateral (ver cv2.bilateralFilter).
        Mayor = más agresivo. Default 25.
    bilateral_sigma_space : float
        σ espacial en el filtro bilateral. Default 7.
    progress_cb : callable(done, total) | None
        Callback opcional llamado tras cada tile procesado (solo en modo tiled).

    Returns
    -------
    dict con métricas útiles para diagnóstico:
      mean, eigenvalues, eigenvectors, target_std, low, high, regularization,
      window, elapsed_s, output, shape, band_indices, saturation_pct,
      mode, n_tiles, tile_size, bilateral_d
    """

    from osgeo import gdal

    gdal.UseExceptions()

    t0 = time.perf_counter()

    band_indices = tuple(int(b) for b in band_indices)
    if len(band_indices) != 3:
        raise ValueError("Se requieren exactamente 3 bandas para decorrelation stretch.")
    if saturation_pct < 0 or saturation_pct > 10:
        raise ValueError("saturation_pct debe estar entre 0 y 10.")
    if tile_size < 64:
        raise ValueError("tile_size debe ser al menos 64 px.")

    ds = gdal.Open(src_path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"No se pudo abrir el raster: {src_path}")

    full_width = ds.RasterXSize
    full_height = ds.RasterYSize
    n_bands = ds.RasterCount

    for b in band_indices:
        if b < 1 or b > n_bands:
            raise ValueError(
                f"Banda {b} fuera de rango — el raster tiene {n_bands} bandas."
            )

    # Resolver la ventana de lectura -----------------------------------------
    if window is None:
        xoff, yoff = 0, 0
        xsize, ysize = full_width, full_height
    else:
        xoff, yoff, xsize, ysize = (int(v) for v in window)
        # Clampeamos contra los límites del raster para tolerar pequeños excesos
        xoff = max(0, min(xoff, full_width - 1))
        yoff = max(0, min(yoff, full_height - 1))
        xsize = max(1, min(xsize, full_width - xoff))
        ysize = max(1, min(ysize, full_height - yoff))

    width = xsize
    height = ysize
    total_px = xsize * ysize
    use_tiled = total_px > in_memory_limit

    # Crea el GeoTIFF de salida preservando georreferenciación ----------------
    driver = gdal.GetDriverByName("GTiff")
    dst_ds = driver.Create(
        dst_path,
        width,
        height,
        3,
        gdal.GDT_Byte,
        options=["COMPRESS=DEFLATE", "TILED=YES", "PREDICTOR=2", "BIGTIFF=IF_SAFER"],
    )
    if dst_ds is None:
        raise RuntimeError(f"No se pudo crear el raster de salida: {dst_path}")

    # Ajusta el geotransform al offset de la ventana: el origen del output
    # se corre (xoff, yoff) píxeles desde el origen del raster fuente.
    src_gt = ds.GetGeoTransform()
    new_gt = (
        src_gt[0] + xoff * src_gt[1] + yoff * src_gt[2],
        src_gt[1],
        src_gt[2],
        src_gt[3] + xoff * src_gt[4] + yoff * src_gt[5],
        src_gt[4],
        src_gt[5],
    )
    dst_ds.SetGeoTransform(new_gt)
    dst_ds.SetProjection(ds.GetProjection())
    # Los GCPs solo tienen sentido sobre el raster entero, no sobre una ventana.
    if ds.GetGCPCount() > 0 and window is None:
        dst_ds.SetGCPs(ds.GetGCPs(), ds.GetGCPProjection())

    channel_names = ("R_dstretch", "G_dstretch", "B_dstretch")
    for i in range(3):
        band_out = dst_ds.GetRasterBand(i + 1)
        band_out.SetNoDataValue(0)
        band_out.SetDescription(channel_names[i])

    n_tiles = 0
    if use_tiled:
        # PASADA 1 — estimar parámetros desde un thumbnail decimado de toda
        # la región. Memoria acotada (~sample_limit píxeles).
        thumb, thumb_mask = _read_thumbnail_sample(
            ds, band_indices, xoff, yoff, xsize, ysize, sample_limit
        )
        X_all = thumb.reshape(-1, 3)
        valid_flat = ~thumb_mask.reshape(-1)
        X_sample = X_all[valid_flat]
        params = _fit_stretch_params(
            X_sample,
            saturation_pct=saturation_pct,
            regularization=regularization,
        )

        # PASADA 2 — aplicar la transformación ya fija sobre cada tile.
        # Si bilateral_d > 0, _process_tiled lee halos para evitar costuras.
        n_tiles = _process_tiled(
            ds,
            dst_ds,
            band_indices,
            xoff,
            yoff,
            xsize,
            ysize,
            params,
            saturation_pct=saturation_pct,
            tile_size=tile_size,
            bilateral_d=bilateral_d,
            bilateral_sigma_color=bilateral_sigma_color,
            bilateral_sigma_space=bilateral_sigma_space,
            progress_cb=progress_cb,
        )
        mode = "tiled"
    else:
        # Camino en memoria: una sola pasada, lee todo de una. Usamos
        # exactamente el mismo par _fit_stretch_params / _apply_stretch_params
        # que el camino tiled, para que ambos sean estadísticamente equivalentes.
        bands_arr = []
        nodata_masks = []
        for bi in band_indices:
            band = ds.GetRasterBand(bi)
            arr = band.ReadAsArray(xoff, yoff, xsize, ysize).astype(
                np.float32, copy=False
            )
            nodata = band.GetNoDataValue()
            mask = (arr == nodata) if nodata is not None else np.zeros_like(arr, dtype=bool)
            bands_arr.append(arr)
            nodata_masks.append(mask)

        img = np.stack(bands_arr, axis=-1)
        combined_mask = np.any(np.stack(nodata_masks, axis=-1), axis=-1)
        combined_mask = combined_mask | np.all(img == 0, axis=-1)

        X = img.reshape(-1, 3)
        valid_flat = ~combined_mask.reshape(-1)
        X_valid = X[valid_flat]
        if X_valid.shape[0] > sample_limit:
            rng = np.random.default_rng(42)
            idx = rng.choice(X_valid.shape[0], size=sample_limit, replace=False)
            X_sample = X_valid[idx]
        else:
            X_sample = X_valid
        params = _fit_stretch_params(
            X_sample,
            saturation_pct=saturation_pct,
            regularization=regularization,
        )

        out = _apply_stretch_params(
            img, params, nodata_mask=combined_mask, saturation_pct=saturation_pct
        )

        # Filtro bilateral opcional. En modo in-memory es trivial: filtramos
        # la salida completa y listo — no hay halos ni tiles. Después volvemos
        # a aplicar la máscara de nodata porque el filtro podría haber
        # "contaminado" los bordes de nodata con valores de píxeles vecinos.
        if bilateral_d > 0:
            out = _apply_bilateral_filter(
                out,
                d=bilateral_d,
                sigma_color=bilateral_sigma_color,
                sigma_space=bilateral_sigma_space,
            )
            if combined_mask.any():
                out[combined_mask] = 0

        for i in range(3):
            dst_ds.GetRasterBand(i + 1).WriteArray(out[..., i])
        mode = "in_memory"

    dst_ds.FlushCache()
    dst_ds = None
    ds = None

    elapsed = time.perf_counter() - t0
    return {
        "mean": params["mu"].tolist(),
        "eigenvalues": params["eigvals"].tolist(),
        "eigenvectors": params["eigvecs"].tolist(),
        "target_std": float(params["target_std"]),
        "low": params["low"].tolist(),
        "high": params["high"].tolist(),
        "regularization": float(params["regularization"]),
        "window": (xoff, yoff, xsize, ysize),
        "elapsed_s": elapsed,
        "output": dst_path,
        "shape": (height, width),
        "band_indices": band_indices,
        "saturation_pct": saturation_pct,
        "mode": mode,
        "n_tiles": n_tiles,
        "tile_size": tile_size,
        "bilateral_d": int(bilateral_d),
    }
