'''solo llama funciones.'''

from enhancement.io import read_geotiff, save_png
from enhancement.color_ramp import apply_color_ramp
from enhancement.decorrelation import decorrelation_stretch

INPUT_GEOTIFF = "/Users/personal/Downloads/CerroUnita_ortomosaico.tif"
OUTPUT_DIR = "data/demo/output/"
BAND_INDEX = 1

if __name__ == "__main__":
    data, profile = read_geotiff(INPUT_GEOTIFF)

    # Color ramp viridis
    result = apply_color_ramp(data, band_index=BAND_INDEX, colormap="viridis")
    save_png(result, f"{OUTPUT_DIR}color_ramp_viridis.png", "Color Ramp — viridis")

    # Color ramp RdYlGn
    result = apply_color_ramp(data, band_index=BAND_INDEX, colormap="RdYlGn")
    save_png(result, f"{OUTPUT_DIR}color_ramp_RdYlGn.png", "Color Ramp — RdYlGn")

    # Decorrelation stretch
    if data.shape[0] >= 3:
        result = decorrelation_stretch(data, band_indices=(1, 2, 3))
        save_png(result, f"{OUTPUT_DIR}decorrelation_stretch.png", "Decorrelation Stretch")
    else:
        print(f"Solo {data.shape[0]} banda(s) — decorrelation stretch requiere 3")

    print("\n✅ Listo! Revisa los resultados en:", OUTPUT_DIR)