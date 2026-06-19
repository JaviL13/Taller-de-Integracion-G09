# -*- coding: utf-8 -*-
"""
sam_wrapper.py — TIGS-70

Wrapper para MobileSAM que:
  1. Carga el modelo UNA SOLA VEZ al iniciar el servidor (evita overhead
     de carga por request).
  2. Proporciona una función `run_sam` que recibe una imagen y opcionalmente
     puntos de prompt, y devuelve la máscara binaria y el score de confianza.
  3. Si no se pasan puntos, usa el punto central de la imagen como prompt
     automáticamente.

MobileSAM es más ligero que SAM original pero sigue siendo un modelo
robusto de segmentación. La API es compatible con la de SAM estándar.
"""

from typing import Optional, Tuple

import numpy as np
import torch

# Importar MobileSAM. La estructura es:
#   from mobile_sam import sam_model_registry
# y luego:
#   model = sam_model_registry["vit_t"](checkpoint=...)
# El modelo se puede encontrar en:
#   https://github.com/ChaoningZhang/MobileSAM
try:
    from mobile_sam import SamPredictor, sam_model_registry
except ImportError:
    raise ImportError(
        "No se pudo importar MobileSAM. Ejecuta pip install -r requirements.txt "
        "en el backend para instalar mobile-sam y sus dependencias."
    )

# Ruta al checkpoint del modelo. En producción, el archivo debería estar
# empaquetado con el backend (p.ej. en una carpeta 'models/').
# Para pruebas, MobileSAM lo descarga automáticamente.
MODEL_PATH = None  # None = descargar automáticamente


# Variable global para la instancia del modelo. Se carga al iniciar.
_sam_model = None
_sam_predictor = None
_device = None


def initialize_sam():
    """Carga el modelo MobileSAM al iniciar el servidor FastAPI.

    Esta función debe llamarse UNA SOLA VEZ desde main.py en el lifespan
    o al inicio del servidor, para evitar cargar el modelo por cada request.
    """
    global _sam_model, _sam_predictor, _device

    if _sam_model is not None:
        return  # Ya está cargado

    # Seleccionar dispositivo (GPU si está disponible, sino CPU)
    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[SAM] Usando dispositivo: {_device}")

    try:
        # Cargar el modelo vit_t (version "tiny", más rápida que vit_h)
        # Los registros disponibles en MobileSAM son típicamente:
        #   - "vit_t": tiny (más rápido)
        #   - "vit_b": base
        #   - "vit_h": huge (más preciso pero lento)
        model = sam_model_registry["vit_t"](checkpoint=MODEL_PATH)
        model.to(_device)
        model.eval()  # Modo inferencia (no se actualizan pesos)
        _sam_model = model
        _sam_predictor = SamPredictor(model)
        print(f"[SAM] Modelo MobileSAM cargado exitosamente en {_device}")
    except Exception as e:
        raise RuntimeError(f"No se pudo cargar el modelo MobileSAM: {e}") from e


def run_sam(
    image: np.ndarray,
    points: Optional[np.ndarray] = None,
    labels: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, float]:
    """Ejecuta MobileSAM sobre una imagen con puntos de prompt opcionales.

    Parámetros:
        image: imagen RGB como np.ndarray de forma (H, W, 3) con valores
               en [0, 255] (uint8) o [0, 1] (float).
        points: opcional, puntos de prompt como np.ndarray de forma (N, 2)
                con [x, y] en píxeles. Si no se pasa, usa el punto central.
        labels: opcional, etiquetas asociadas a los puntos:
                1 = foreground (incluir en máscara)
                0 = background (excluir de máscara)
                Si no se pasa, todos los puntos son foreground (1).

    Retorna:
        (mask, confidence): tupla con:
          - mask: máscara binaria (H, W) uint8 con valores 0 (fondo) o 255 (objeto).
          - confidence: float en [0, 1] que estima la confianza del modelo.
                       Se calcula como la media de las probabilidades
                       de la máscara (score del predictor).
    """
    if _sam_model is None or _sam_predictor is None:
        raise RuntimeError("El modelo SAM no ha sido inicializado. Llama a initialize_sam() primero.")

    # MobileSAM espera imagen RGB uint8 en [0, 255].
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)

    # Si no se pasan puntos, usar cuadrícula 3×3 para mejor cobertura del ROI
    if points is None:
        h, w = image.shape[:2]
        xs = [w // 4, w // 2, 3 * w // 4]
        ys = [h // 4, h // 2, 3 * h // 4]
        points = np.array([[x, y] for y in ys for x in xs], dtype=np.float32)
        labels = np.ones(len(points), dtype=np.int32)

    # Si se pasan puntos pero no labels, asumir todos foreground
    if labels is None:
        labels = np.ones(len(points), dtype=np.int32)

    # Pasar imagen al modelo (MobileSAM espera float32 en [0, 1])
    try:
        # Procesar la imagen con el predictor de MobileSAM.
        _sam_predictor.set_image(image)

        # Ejecutar predicción con puntos de prompt — 3 candidatos para elegir el mejor
        masks, scores, logits = _sam_predictor.predict(
            point_coords=points,
            point_labels=labels,
            multimask_output=True,
        )
        # Seleccionar la máscara con mayor score
        best_idx = int(np.argmax(scores))
        mask_binary = masks[best_idx]
        confidence = float(scores[best_idx])
        mask_output = (mask_binary * 255).astype(np.uint8)

    except Exception as e:
        raise RuntimeError(f"Error durante la inferencia con MobileSAM: {e}") from e

    return mask_output, confidence
