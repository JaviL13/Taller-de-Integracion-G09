# -*- coding: utf-8 -*-
"""Pruebas unitarias del módulo decorrelation_stretch.

Valida los criterios de aceptación:
  - PCA se aplica sobre 3 bandas del GeoTIFF.
  - Resultado es un raster georreferenciado con las mismas dimensiones.
  - Tiempo de procesamiento para 2000×2000 px < 10 segundos.
  - Las bandas de entrada son configurables.

Los tests marcados `@pytest.mark.gdal` requieren `osgeo.gdal` (disponible dentro
de QGIS). El resto verifica el núcleo matemático con numpy puro.
"""

import os
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decorrelation_stretch import (  # noqa: E402
    _apply_stretch_params,
    _bilateral_filter_numpy,
    _decorrelation_stretch_array,
    _fit_stretch_params,
)

try:
    from osgeo import gdal, osr  # noqa: F401

    HAS_GDAL = True
except ImportError:
    HAS_GDAL = False


# ----------------------------------------------------------------------------
# Núcleo matemático (no requiere GDAL)
# ----------------------------------------------------------------------------


def _make_correlated_rgb(height, width, seed=0):
    """Bandas altamente correlacionadas, como ortofoto de desierto."""
    rng = np.random.default_rng(seed)
    lat = rng.normal(128, 40, size=(height, width, 3)).astype(np.float32)
    mix = np.array(
        [[0.6, 0.3, 0.1], [0.3, 0.6, 0.1], [0.1, 0.3, 0.6]], dtype=np.float32
    )
    img = np.einsum("hwc,cn->hwn", lat, mix)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_core_returns_uint8_same_shape():
    img = _make_correlated_rgb(128, 128)
    out, stats = _decorrelation_stretch_array(img)
    assert out.dtype == np.uint8
    assert out.shape == img.shape
    expected_keys = {
        "mean",
        "eigenvalues",
        "eigenvectors",
        "target_std",
        "low",
        "high",
    }
    assert expected_keys.issubset(stats.keys())


def test_core_decorrelates_channels():
    """Tras el stretch, la correlación entre canales debe bajar."""
    img = _make_correlated_rgb(256, 256, seed=1).astype(np.float32)
    out, _ = _decorrelation_stretch_array(img)
    out = out.astype(np.float32)

    src_corr = np.corrcoef(img.reshape(-1, 3).T)
    dst_corr = np.corrcoef(out.reshape(-1, 3).T)
    src_off = np.abs(src_corr - np.eye(3)).sum()
    dst_off = np.abs(dst_corr - np.eye(3)).sum()
    assert dst_off < src_off, (
        f"Corr fuera-de-diag NO disminuyó: src={src_off:.2f} dst={dst_off:.2f}"
    )


def test_core_respects_nodata_mask():
    img = _make_correlated_rgb(64, 64, seed=2)
    mask = np.zeros((64, 64), dtype=bool)
    mask[:8, :] = True  # las primeras 8 filas son nodata
    out, _ = _decorrelation_stretch_array(img, nodata_mask=mask)
    assert np.all(out[:8, :, :] == 0)
    # Resto no debería ser todo cero
    assert out[8:, :, :].sum() > 0


def test_core_rejects_bad_shape():
    img = np.zeros((10, 10, 4), dtype=np.uint8)
    with pytest.raises(ValueError):
        _decorrelation_stretch_array(img)


def test_core_different_bands_yield_different_results():
    """Si el usuario elige bandas distintas, el resultado cambia."""
    rng = np.random.default_rng(3)
    stack = rng.integers(0, 255, size=(128, 128, 4), dtype=np.uint8)
    # PCA sobre (1,2,3) vs (2,3,4) → resultados distintos
    a, _ = _decorrelation_stretch_array(stack[..., (0, 1, 2)].astype(np.uint8))
    b, _ = _decorrelation_stretch_array(stack[..., (1, 2, 3)].astype(np.uint8))
    assert not np.array_equal(a, b)


def test_fit_and_apply_match_full_core():
    """_fit_stretch_params + _apply_stretch_params sobre la imagen completa
    debe ser equivalente al resultado de _decorrelation_stretch_array."""
    img = _make_correlated_rgb(96, 96, seed=11)
    X = img.astype(np.float32).reshape(-1, 3)
    mask = np.all(img == 0, axis=-1)
    X_valid = X[~mask.reshape(-1)]

    params = _fit_stretch_params(X_valid, saturation_pct=1.0)
    applied = _apply_stretch_params(img, params, saturation_pct=1.0)
    baseline, _ = _decorrelation_stretch_array(img, saturation_pct=1.0)

    # Con la misma muestra de píxeles, el resultado debe ser idéntico.
    assert np.array_equal(applied, baseline)


def test_regularization_caps_stretch_matrix_norm():
    """Sobre una distribución con "estructura de cigarro" (un eje domina,
    dos son mucho más chicos — típica de ortofotos de desierto), la
    regularización debe producir una matriz M con norma MENOR que la
    canónica. Eso prueba que la amplificación global de la transformación
    está acotada, que es justo el mecanismo que reduce el ruido.

    Optamos por testear la matriz directamente (no una imagen generada)
    porque es más determinístico y captura la intención matemática."""
    rng = np.random.default_rng(42)
    n = 5000
    # Eje principal: variación grande en dirección diagonal (1, 1, 1).
    # Esto simula la dimensión "brillo" de un ortofoto de desierto.
    t = rng.normal(0, 40.0, size=n).astype(np.float32)
    primary = np.outer(t, [1.0, 1.0, 1.0]).astype(np.float32)
    # Ruido chico en los 3 canales independientes — los ejes perpendiculares.
    noise = rng.normal(0, 2.0, size=(n, 3)).astype(np.float32)
    X = primary + noise + np.array([128.0, 128.0, 128.0], dtype=np.float32)

    params_raw = _fit_stretch_params(X, saturation_pct=0.0, regularization=0.0)
    params_reg = _fit_stretch_params(
        X, saturation_pct=0.0, regularization=0.05)

    # La norma Frobenius de M mide "cuánto estira en total" la transformación.
    # Con regularización, los ejes chicos se estiran menos → M tiene norma
    # menor.
    norm_raw = float(np.linalg.norm(params_raw["M"]))
    norm_reg = float(np.linalg.norm(params_reg["M"]))

    assert norm_reg < norm_raw, (
        f"La regularización no redujo la norma de M: raw={norm_raw:.2f}, "
        f"reg={norm_reg:.2f}"
    )
    # Además, con regularización la matriz debe estar mejor condicionada
    # (autovalores más parejos tras el inverso).
    cond_raw = params_raw["eigvals"].max() / params_raw["eigvals"].min()
    # cond_reg = params_reg["eigvals"].max() / params_reg["eigvals"].min()
    # La regularización no cambia los eigvals originales que guardamos en
    # params, pero sí cambia el factor k/√λ usado internamente — este assert
    # sirve como sanity check de que el cigarro es realmente un cigarro.
    assert cond_raw > 10, f"Setup del test mal: cigarro no es cigarro (cond={cond_raw})"


def test_regularization_zero_is_backward_compatible():
    """regularization=0 debe dar exactamente el mismo resultado que la
    versión sin el parámetro (garantía de compatibilidad hacia atrás)."""
    img = _make_correlated_rgb(96, 96, seed=33)
    out_default, stats_default = _decorrelation_stretch_array(img)
    out_explicit, stats_explicit = _decorrelation_stretch_array(
        img, regularization=0.0
    )
    assert np.array_equal(out_default, out_explicit)
    assert stats_default["regularization"] == 0.0


def test_regularization_validates_range():
    """Rechazar valores fuera de [0, 1]."""
    img = _make_correlated_rgb(32, 32, seed=44)
    with pytest.raises(ValueError):
        _decorrelation_stretch_array(img, regularization=-0.1)
    with pytest.raises(ValueError):
        _decorrelation_stretch_array(img, regularization=1.5)


def test_tiled_application_matches_full_image():
    """Aplicar la transformación tile-por-tile con los mismos params debe
    ser exactamente equivalente a aplicarla a la imagen completa.
    Este invariante es lo que hace correcto el camino tiled en GDAL."""
    img = _make_correlated_rgb(200, 200, seed=22)
    X = img.astype(np.float32).reshape(-1, 3)
    mask = np.all(img == 0, axis=-1)
    X_valid = X[~mask.reshape(-1)]
    params = _fit_stretch_params(X_valid, saturation_pct=1.0)

    # Aplicación completa
    full = _apply_stretch_params(img, params, saturation_pct=1.0)

    # Aplicación por teselas
    tile_size = 64
    H, W, _ = img.shape
    tiled = np.zeros_like(full)
    for y in range(0, H, tile_size):
        for x in range(0, W, tile_size):
            th = min(tile_size, H - y)
            tw = min(tile_size, W - x)
            tile = img[y: y + th, x: x + tw, :]
            out_tile = _apply_stretch_params(tile, params, saturation_pct=1.0)
            tiled[y: y + th, x: x + tw, :] = out_tile

    assert np.array_equal(full, tiled)


def test_bilateral_numpy_preserves_shape_and_dtype():
    """El fallback numpy del bilateral debe devolver uint8 con la misma
    forma que la entrada."""
    rng = np.random.default_rng(55)
    img = rng.integers(0, 255, size=(64, 64, 3), dtype=np.uint8)
    out = _bilateral_filter_numpy(img, d=5, sigma_color=20.0, sigma_space=5.0)
    assert out.shape == img.shape
    assert out.dtype == np.uint8


def test_bilateral_numpy_reduces_noise_in_flat_region():
    """Sobre un cuadro uniforme con ruido gaussiano, el bilateral numpy
    debe reducir significativamente la varianza del ruido. Es el test
    funcional de que el filtro realmente suaviza."""
    rng = np.random.default_rng(56)
    base = np.array([128, 100, 80], dtype=np.float32)
    noise = rng.normal(0, 10.0, size=(80, 80, 3)).astype(np.float32)
    img = np.clip(base + noise, 0, 255).astype(np.uint8)

    filtered = _bilateral_filter_numpy(
        img, d=7, sigma_color=25.0, sigma_space=7.0)

    var_before = img.astype(np.float32).var(axis=(0, 1)).mean()
    var_after = filtered.astype(np.float32).var(axis=(0, 1)).mean()
    # Con kernel d=7 y sigma_color=25 (>> σ del ruido), esperamos reducción
    # de al menos 50 % en zonas uniformes.
    assert var_after < var_before * 0.5, (
        f"Bilateral no suavizó suficiente: antes={var_before:.1f}, "
        f"después={var_after:.1f}"
    )


def test_bilateral_numpy_preserves_edges():
    """El filtro bilateral NO debe borronear bordes fuertes. Creamos una
    imagen mitad negra / mitad blanca y verificamos que el salto de
    intensidad en la frontera se mantiene casi intacto."""
    img = np.zeros((40, 40, 3), dtype=np.uint8)
    img[:, 20:, :] = 255  # borde vertical fuerte en la mitad

    filtered = _bilateral_filter_numpy(
        img, d=7, sigma_color=25.0, sigma_space=7.0
    )

    # La diferencia entre la columna 19 (negra) y la 20 (blanca) debe
    # seguir siendo alta. Un blur gaussiano la bajaría a ~128; el bilateral
    # la mantiene >200 porque σ_color=25 corta el promediado entre lados.
    step = int(filtered[20, 20, 0]) - int(filtered[20, 19, 0])
    assert step > 200, f"El filtro borroneó el borde: step={step}"


@pytest.mark.benchmark
def test_core_performance_2000x2000_under_10s():
    """Criterio de aceptación: < 10 s para regiones de hasta 2000×2000 px."""
    img = _make_correlated_rgb(2000, 2000, seed=4)
    t0 = time.perf_counter()
    out, _ = _decorrelation_stretch_array(img)
    elapsed = time.perf_counter() - t0
    assert out.shape == img.shape
    assert elapsed < 10.0, f"Demasiado lento: {elapsed:.2f} s"


# ----------------------------------------------------------------------------
# Integración completa (requiere GDAL — corre dentro de QGIS o entorno con osgeo)
# ----------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_GDAL, reason="osgeo.gdal no disponible")
def test_gdal_preserves_georef(tmp_path):
    from decorrelation_stretch import decorrelation_stretch

    src_path = str(tmp_path / "src.tif")
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(src_path, 256, 256, 3, gdal.GDT_Byte)
    ds.SetGeoTransform([500000.0, 0.5, 0.0, 7500000.0, 0.0, -0.5])
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32719)
    ds.SetProjection(srs.ExportToWkt())
    img = _make_correlated_rgb(256, 256)
    for i in range(3):
        ds.GetRasterBand(i + 1).WriteArray(img[..., i])
    ds.FlushCache()
    ds = None

    out = str(tmp_path / "out.tif")
    info = decorrelation_stretch(src_path, out, band_indices=(1, 2, 3))

    src = gdal.Open(src_path)
    dst = gdal.Open(out)
    assert dst.RasterCount == 3
    assert dst.RasterXSize == src.RasterXSize
    assert dst.RasterYSize == src.RasterYSize
    assert dst.GetGeoTransform() == src.GetGeoTransform()
    assert dst.GetProjection() == src.GetProjection()
    assert info["elapsed_s"] < 10.0
