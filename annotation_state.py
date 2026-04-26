# -*- coding: utf-8 -*-
"""Módulo de estado para anotaciones (TIGS-64).

Single source of truth de:
  - Qué estados existen ('pending', 'approved', 'rejected').
  - Qué transiciones entre estados son válidas.
  - Qué color se usa para pintar cada estado en el mapa.

Este módulo es PURE PYTHON: no importa qgis, ni PyQt5, ni nada que
requiera tener QGIS instalado. Eso permite testearlo en CI (donde no
hay QGIS) y lo hace reusable desde el backend si en el futuro se
necesita aplicar las mismas reglas server-side.

Los strings de los estados ('pending', 'approved', 'rejected') coinciden
exactamente con el CHECK constraint de la columna `status` del esquema
MER (ver scripts/init_gpkg.py / TIGS-45). Mantenerlos sincronizados es
importante: si se desalinean, los UPDATE/INSERT al .gpkg fallan en runtime.
"""

from enum import Enum


class AnnotationState(str, Enum):
    """Estados posibles de una anotación.

    Hereda de str además de Enum para que `AnnotationState.PENDING == "pending"`
    sea True; eso simplifica el interop con QGIS (que devuelve strings al
    leer el campo del feature) y con el .gpkg.
    """
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class StateTransitionError(ValueError):
    """La transición de estado solicitada no está permitida."""
    pass


# Tabla de transiciones permitidas. Llave = estado origen, valor = set
# de estados destino válidos. Cualquier transición fuera de esta tabla
# se rechaza con StateTransitionError.
#
# Regla: se puede pasar entre cualquier par de estados DISTINTOS. La
# única transición prohibida es estado→sí mismo, porque no representa
# un cambio real (y persistirla recarga sin sentido el campo updated_at).
_TRANSICIONES_VALIDAS = {
    AnnotationState.PENDING: {
        AnnotationState.APPROVED,
        AnnotationState.REJECTED,
    },
    AnnotationState.APPROVED: {
        AnnotationState.PENDING,
        AnnotationState.REJECTED,
    },
    AnnotationState.REJECTED: {
        AnnotationState.PENDING,
        AnnotationState.APPROVED,
    },
}


# Colores RGBA por estado, en formato (R, G, B, alpha) sobre 255.
# Alpha 100 = ~40% transparencia para que el raster siga siendo visible
# debajo del polígono. Esquema flat-UI con buen contraste sobre fondo
# oscuro (típico de imágenes satelitales de Atacama).
_COLORES = {
    AnnotationState.PENDING:  (243, 156, 18, 100),   # naranja — necesita revisión
    AnnotationState.APPROVED: (39, 174, 96, 100),    # verde — confirmado
    AnnotationState.REJECTED: (231, 76, 60, 100),    # rojo — descartado
}


def parse_state(value) -> AnnotationState:
    """Parsea un valor (string o AnnotationState) al enum, o lanza ValueError.

    Es conveniencia para llamantes que reciben el campo crudo desde el
    .gpkg (que devuelve strings, no enums).
    """
    if isinstance(value, AnnotationState):
        return value
    try:
        return AnnotationState(value)
    except ValueError as e:
        validos = [s.value for s in AnnotationState]
        raise ValueError(
            f"Estado inválido: {value!r}. Estados válidos: {validos}"
        ) from e


def validate_transition(origen, destino) -> None:
    """Valida que la transición origen→destino sea permitida.

    Lanza StateTransitionError si no lo es. No retorna nada si está bien.
    Acepta tanto AnnotationState como strings crudos (los parsea internamente).
    """
    origen = parse_state(origen)
    destino = parse_state(destino)
    if destino not in _TRANSICIONES_VALIDAS[origen]:
        raise StateTransitionError(
            f"Transición no permitida: {origen.value} → {destino.value}"
        )


def color_for_state(state) -> tuple:
    """Devuelve la tupla (R, G, B, alpha) que se debe usar para pintar
    el polígono asociado a este estado.

    Acepta AnnotationState o string. Los valores son sobre 255 (rango
    estándar de QColor de Qt).
    """
    return _COLORES[parse_state(state)]
