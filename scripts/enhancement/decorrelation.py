'''algoritmo decorrelation stretch
igual, la TIGS-38 lo reutiliza directo.
El algoritmo es un poco más complejo: toma 3 bandas,
las centra, calcula la matriz de covarianza, obtiene los
eigenvalores y eigenvectores, proyecta los datos en el espacio PCA,
estira cada componente usando percentiles 2-98, y luego proyecta de vuelta
al espacio original.
La función decorrelation_stretch retorna un array RGB uint8 listo
para guardar como PNG o mostrar en QGIS.'''

import numpy as np


def decorrelation_stretch(data, band_indices=(1, 2, 3)):
    """
    Decorrelation stretch sobre 3 bandas usando PCA.
    Retorna imagen RGB como array uint8.
    """
    bands = np.stack([
        data[i - 1].astype(np.float32)
        for i in band_indices
    ], axis=-1)

    H, W, _ = bands.shape
    pixels = bands.reshape(-1, 3)

    valid_mask = ~np.any(np.isnan(pixels), axis=1)
    pixels_valid = pixels[valid_mask]

    mean = np.mean(pixels_valid, axis=0)
    centered = pixels_valid - mean
    cov = np.cov(centered.T)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    projected = centered @ eigenvectors

    stretched = np.zeros_like(projected)
    for i in range(3):
        p2, p98 = np.percentile(projected[:, i], [2, 98])
        stretched[:, i] = np.clip(
            (projected[:, i] - p2) / (p98 - p2 + 1e-8), 0, 1)

    result_valid = stretched @ eigenvectors.T + mean
    result = np.zeros((H * W, 3), dtype=np.float32)
    result[valid_mask] = result_valid
    result = np.clip(result.reshape(H, W, 3), 0, 1)

    return (result * 255).astype(np.uint8)
