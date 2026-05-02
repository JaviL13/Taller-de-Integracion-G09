# -*- coding: utf-8 -*-
"""Tests del módulo annotation_state (TIGS-64).

Estos tests son PURE PYTHON: no dependen de QGIS ni de PyQt5, así que
corren sin problemas en CI (GitHub Actions sin instalación de QGIS).

Cubren:
  - Integridad del enum AnnotationState (valores y herencia de str).
  - parse_state: acepta strings y enums, rechaza basura.
  - validate_transition: acepta transiciones válidas, lanza
    StateTransitionError en las inválidas.
  - color_for_state: devuelve la tupla RGBA esperada para cada estado.
"""
import os
import sys

import pytest

# Agregar el root del repo al sys.path para poder importar annotation_state
# como módulo top-level (igual que el resto de los tests del proyecto).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from annotation_state import (  # noqa: E402
    AnnotationState,
    StateTransitionError,
    color_for_state,
    parse_state,
    validate_transition,
)


# ── Integridad del enum ───────────────────────────────────────────────────

def test_enum_tiene_los_tres_estados_esperados():
    """El enum debe tener exactamente PENDING, APPROVED, REJECTED."""
    valores = {s.value for s in AnnotationState}
    assert valores == {"pending", "approved", "rejected"}


def test_enum_hereda_de_str():
    """AnnotationState.PENDING == 'pending' debe ser True (interop con .gpkg)."""
    assert AnnotationState.PENDING == "pending"
    assert AnnotationState.APPROVED == "approved"
    assert AnnotationState.REJECTED == "rejected"


# ── parse_state ───────────────────────────────────────────────────────────

def test_parse_state_acepta_string_valido():
    assert parse_state("pending") is AnnotationState.PENDING
    assert parse_state("approved") is AnnotationState.APPROVED
    assert parse_state("rejected") is AnnotationState.REJECTED


def test_parse_state_acepta_enum_directo():
    """Si ya viene como enum, debe devolverlo tal cual (idempotente)."""
    assert parse_state(AnnotationState.PENDING) is AnnotationState.PENDING


def test_parse_state_rechaza_string_invalido():
    with pytest.raises(ValueError) as exc_info:
        parse_state("foo")
    # El mensaje de error debe incluir los estados válidos para ayudar
    # a debuggear.
    assert "pending" in str(exc_info.value)
    assert "approved" in str(exc_info.value)
    assert "rejected" in str(exc_info.value)


def test_parse_state_rechaza_none():
    with pytest.raises(ValueError):
        parse_state(None)


# ── validate_transition: transiciones válidas ───────────────────────────

@pytest.mark.parametrize(
    "origen,destino",
    [
        (AnnotationState.PENDING, AnnotationState.APPROVED),
        (AnnotationState.PENDING, AnnotationState.REJECTED),
        (AnnotationState.APPROVED, AnnotationState.REJECTED),
        (AnnotationState.APPROVED, AnnotationState.PENDING),
        (AnnotationState.REJECTED, AnnotationState.APPROVED),
        (AnnotationState.REJECTED, AnnotationState.PENDING),
    ],
)
def test_validate_transition_acepta_transiciones_entre_estados_distintos(
    origen, destino
):
    """Cualquier transición entre estados DISTINTOS debe ser permitida."""
    # No debe lanzar nada.
    validate_transition(origen, destino)


def test_validate_transition_acepta_strings_crudos():
    """Como los .gpkg devuelven strings, validate_transition debe aceptarlos."""
    validate_transition("pending", "approved")
    validate_transition("approved", "rejected")


# ── validate_transition: transiciones inválidas (estado→sí mismo) ────────

@pytest.mark.parametrize(
    "estado",
    list(AnnotationState),
)
def test_validate_transition_rechaza_estado_a_si_mismo(estado):
    """Una transición de un estado a sí mismo no es un cambio real."""
    with pytest.raises(StateTransitionError):
        validate_transition(estado, estado)


def test_state_transition_error_es_subclase_de_value_error():
    """StateTransitionError debe ser ValueError para que el llamante
    pueda capturarlo con `except ValueError` si quisiera ser genérico.
    """
    assert issubclass(StateTransitionError, ValueError)


# ── color_for_state ──────────────────────────────────────────────────────

def test_color_for_state_devuelve_tupla_rgba_para_cada_estado():
    """Cada estado debe tener un color RGBA distinto."""
    colores = {color_for_state(s) for s in AnnotationState}
    # Si todos fueran iguales el set tendría tamaño 1.
    assert len(colores) == 3


def test_color_for_state_pendiente_es_naranja():
    """Pending = naranja (243, 156, 18) — código de color del esquema."""
    r, g, b, a = color_for_state(AnnotationState.PENDING)
    assert (r, g, b) == (243, 156, 18)
    # Alpha debe estar en rango válido [0, 255].
    assert 0 <= a <= 255


def test_color_for_state_approved_es_verde():
    r, g, b, _ = color_for_state(AnnotationState.APPROVED)
    assert (r, g, b) == (39, 174, 96)


def test_color_for_state_rejected_es_rojo():
    r, g, b, _ = color_for_state(AnnotationState.REJECTED)
    assert (r, g, b) == (231, 76, 60)


def test_color_for_state_acepta_string():
    """Si llamamos con string crudo (típico cuando viene del .gpkg) debe funcionar."""
    assert color_for_state("pending") == color_for_state(AnnotationState.PENDING)


def test_color_for_state_rechaza_estado_invalido():
    with pytest.raises(ValueError):
        color_for_state("foo")
