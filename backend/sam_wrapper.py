# -*- coding: utf-8 -*-
"""
sam_wrapper.py

Wrapper para SAM2 que:
  1. Carga el modelo UNA SOLA VEZ al iniciar el servidor (evita overhead
     de carga por request).
  2. Proporciona una función `run_sam` que recibe una imagen y opcionalmente
     puntos de prompt, y devuelve la máscara binaria y el score de confianza.
  3. Si no se pasan puntos, usa una cuadrícula 3×3 como prompt automático.

SAM2 (Segment Anything Model 2) es el sucesor de SAM y MobileSAM, con mejor
precisión y soporte activo de Meta. La API de SAM2ImagePredictor es compatible
con la de SamPredictor de versiones anteriores.
"""

import contextlib
from typing import Optional, Tuple

import numpy as np
import torch

try:
    from sam2.build_sam import build_sam2_hf
    from sam2.sam2_image_predictor import SAM2ImagePredictor
except ImportError:
    raise ImportError(
        "No se pudo importar SAM2. Ejecuta pip install -r requirements.txt "
        "en el backend para instalar sam2 y sus dependencias."
    )

# ID del modelo en HuggingFace. Opciones disponibles (de menor a mayor precisión):
#   "facebook/sam2.1-hiera-tiny"       — más rápido, menos preciso
#   "facebook/sam2.1-hiera-small"      — equilibrio velocidad/precisión (recomendado)
#   "facebook/sam2.1-hiera-base-plus"  — más preciso, más lento
#   "facebook/sam2.1-hiera-large"      — máxima precisión, requiere GPU
MODEL_HF_ID = "facebook/sam2.1-hiera-small"

_sam_predictor: Optional[SAM2ImagePredictor] = None
_device: Optional[torch.device] = None


def initialize_sam():
    """Carga el modelo SAM2 al iniciar el servidor FastAPI.

    Descarga los pesos desde HuggingFace la primera vez (~180MB para hiera-small).
    Las ejecuciones siguientes usan la caché local de HuggingFace.
    """
    global _sam_predictor, _device

    if _sam_predictor is not None:
        return

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[SAM2] Usando dispositivo: {_device}")

    try:
        model = build_sam2_hf(MODEL_HF_ID, device=str(_device))
        _sam_predictor = SAM2ImagePredictor(model)
        print(f"[SAM2] Modelo '{MODEL_HF_ID}' cargado exitosamente en {_device}")
    except Exception as e:
        raise RuntimeError(f"No se pudo cargar el modelo SAM2: {e}") from e


def run_sam(
    image: np.ndarray,
    points: Optional[np.ndarray] = None,
    labels: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, float]:
    """Ejecuta SAM2 sobre una imagen con puntos de prompt opcionales.

    Parámetros:
        image: imagen RGB como np.ndarray de forma (H, W, 3) con valores
               en [0, 255] (uint8) o [0, 1] (float).
        points: opcional, puntos de prompt como np.ndarray de forma (N, 2)
                con [x, y] en píxeles. Si no se pasa, usa cuadrícula 3×3.
        labels: opcional, etiquetas asociadas a los puntos:
                1 = foreground (incluir en máscara)
                0 = background (excluir de máscara)
                Si no se pasa, todos los puntos son foreground (1).

    Retorna:
        (mask, confidence): tupla con:
          - mask: máscara binaria (H, W) uint8 con valores 0 (fondo) o 255 (objeto).
          - confidence: float en [0, 1], score de confianza del modelo.
    """
    if _sam_predictor is None:
        raise RuntimeError("El modelo SAM2 no ha sido inicializado. Llama a initialize_sam() primero.")

    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)

    # box_prompt se usa cuando no hay puntos de usuario (modo automático).
    box_prompt = None

    if points is None:
        h, w = image.shape[:2]
        cx, cy = w // 2, h // 2

        # Foreground: centro más cuatro puntos a 1/8 de distancia del centro.
        # Cluster compacto para indicar el objeto sin cubrir toda la imagen.
        fg_pts = np.array(
            [
                [cx, cy],
                [cx - w // 8, cy],
                [cx + w // 8, cy],
                [cx, cy - h // 8],
                [cx, cy + h // 8],
            ],
            dtype=np.float32,
        )

        # Background: esquinas ligeramente interiores (5% del borde).
        # Decirle a SAM2 que los bordes son fondo fuerza que encuentre el límite
        # real del objeto en lugar de devolver la imagen completa como máscara.
        mx, my = max(1, w // 20), max(1, h // 20)
        bg_pts = np.array(
            [
                [mx, my],  # esquina superior-izquierda
                [w - mx, my],  # esquina superior-derecha
                [mx, h - my],  # esquina inferior-izquierda
                [w - mx, h - my],  # esquina inferior-derecha
            ],
            dtype=np.float32,
        )

        points = np.concatenate([fg_pts, bg_pts], axis=0)
        labels = np.concatenate(
            [
                np.ones(len(fg_pts), dtype=np.int32),  # foreground
                np.zeros(len(bg_pts), dtype=np.int32),  # background
            ]
        )

        # Box prompt: zona interior (70% del área) para reforzar dónde está el objeto.
        pad_x, pad_y = w * 0.15, h * 0.15
        box_prompt = np.array([pad_x, pad_y, w - pad_x, h - pad_y], dtype=np.float32)

    if labels is None:
        labels = np.ones(len(points), dtype=np.int32)

    # En GPU se activa autocast bfloat16 para mejor rendimiento.
    # En CPU se usa solo inference_mode (autocast bfloat16 no aporta en CPU).
    autocast_ctx = (
        torch.autocast("cuda", dtype=torch.bfloat16)
        if _device is not None and _device.type == "cuda"
        else contextlib.nullcontext()
    )

    try:
        with torch.inference_mode(), autocast_ctx:
            _sam_predictor.set_image(image)
            masks, scores, logits = _sam_predictor.predict(
                point_coords=points,
                point_labels=labels,
                box=box_prompt,
                multimask_output=True,
            )

        best_idx = int(np.argmax(scores))
        mask_binary = masks[best_idx]
        confidence = float(scores[best_idx])
        mask_output = (mask_binary * 255).astype(np.uint8)

    except Exception as e:
        raise RuntimeError(f"Error durante la inferencia con SAM2: {e}") from e

    return mask_output, confidence
