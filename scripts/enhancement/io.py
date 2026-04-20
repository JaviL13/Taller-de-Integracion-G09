''' leer/escribir archivos (GeoTIFF, PNG)
 todo lo que toca disco va junto. Si mañana cambian de PNG a GeoTIFF de salida, solo tocas este archivo.
 La función read_geotiff retorna un array 3D (bandas, filas, columnas) y el perfil (metadatos) del archivo.
 La función save_png toma un array RGB uint8 y lo guarda como PNG usando matplotlib.'''

import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os

def read_geotiff(path, max_side=4096):
    """Lee un GeoTIFF y retorna el array y el perfil.

    Si la imagen supera max_side píxeles en alguna dimensión, se lee
    submuestreada para que quepa en memoria durante el prototipado.
    """
    with rasterio.open(path) as src:
        h, w = src.height, src.width
        scale = min(1.0, max_side / max(h, w))
        out_h = max(1, int(h * scale))
        out_w = max(1, int(w * scale))
        data = src.read(out_shape=(src.count, out_h, out_w),
                        resampling=rasterio.enums.Resampling.average)
        profile = src.profile.copy()
        profile.update(height=out_h, width=out_w)
    if scale < 1.0:
        print(f"GeoTIFF cargado (submuestreado {scale:.2%}): "
              f"{data.shape[0]} bandas, {data.shape[1]}x{data.shape[2]} px "
              f"(original {h}x{w})")
    else:
        print(f"GeoTIFF cargado: {data.shape[0]} bandas, {data.shape[1]}x{data.shape[2]} px")
    return data, profile

def save_png(image_array, output_path, title=""):
    """Guarda un array como PNG con matplotlib."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.figure(figsize=(10, 8))
    plt.imshow(image_array)
    plt.title(title)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Guardado: {output_path}")