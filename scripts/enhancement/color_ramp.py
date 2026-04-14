''''algoritmo color ramp
 un módulo por algoritmo. Así la TIGS-37 (color ramp en el plugin) puede importar directamente este mismo archivo sin reescribir nada.
 El algoritmo es simple: toma una banda, la normaliza (percentiles 2-98) y le aplica una paleta de colores (viridis por defecto).
 La función apply_color_ramp retorna un array RGB uint8 listo para guardar como PNG o mostrar en QGIS.'''

import numpy as np
import matplotlib.pyplot as plt

def normalize(band):
    """Normaliza una banda al rango [0, 1] usando percentiles 2-98."""
    b_min = np.nanpercentile(band, 2)
    b_max = np.nanpercentile(band, 98)
    return np.clip((band - b_min) / (b_max - b_min + 1e-8), 0, 1)

def apply_color_ramp(data, band_index=1, colormap="viridis"):
    """
    Aplica una paleta de colores sobre una banda seleccionada.
    Retorna imagen RGB como array uint8.
    """
    band = data[band_index - 1].astype(np.float32)
    band_norm = normalize(band)
    cmap = plt.get_cmap(colormap)
    colored = (cmap(band_norm)[:, :, :3] * 255).astype(np.uint8)
    return colored