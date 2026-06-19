# TIGS 100: Tests de split view
# Estos tests son pure Python: no necesitan QGIS instalado porque mockean todos los objetos de QGIS.
# -*- coding: utf-8 -*-

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mockear qgis antes de importar split_view_manager
for _m in ["qgis", "qgis.core", "qgis.gui", "qgis.PyQt", "qgis.PyQt.QtCore", "qgis.PyQt.QtWidgets"]:
    sys.modules.setdefault(_m, MagicMock())

from split_view_manager import SplitViewManager


# Crea un SplitViewManager con un iface mockeado.
def _make_manager():
    iface = MagicMock()
    # El canvas principal es un mock con extent() y extentsChanged
    canvas_principal = MagicMock()
    iface.mapCanvas.return_value = canvas_principal
    iface.mainWindow.return_value = MagicMock()
    manager = SplitViewManager(iface)
    return manager, iface, canvas_principal


# Test de estado inicial


# El split view debe empezar desactivado.
def test_manager_inicia_inactivo():
    manager, _, _ = _make_manager()
    assert manager.esta_activo() is False


# La sincronización debe estar ON por defecto.
def test_manager_inicia_con_sincronizacion_on():
    manager, _, _ = _make_manager()
    assert manager._sincronizado is True


# El canvas secundario no debe existir antes de activar el split view.
def test_canvas_secundario_es_none_antes_de_activar():
    manager, _, _ = _make_manager()
    assert manager._canvas_secundario is None


# Tests de activar/desactivar


# Después de activar, debe retornar True.
def test_activar_cambia_estado_a_activo():
    manager, _, _ = _make_manager()
    manager.activar()
    assert manager.esta_activo() is True


# Después de desactivar, debe retornar False.
def test_desactivar_cambia_estado_a_inactivo():
    manager, _, _ = _make_manager()
    manager.activar()
    manager.desactivar()
    assert manager.esta_activo() is False


# Llamar activar() dos veces no debe crear dos canvas secundarios.
def test_activar_dos_veces_no_duplica():
    manager, _, _ = _make_manager()
    manager.activar()
    canvas_primera_vez = manager._canvas_secundario
    manager.activar()  # Segunda llamada (debe ignorarse)
    assert manager._canvas_secundario is canvas_primera_vez  # El canvas no debe haber cambiado


# Llamar desactivar() sin haber activado no debe lanzar errores.
def test_desactivar_sin_activar_no_falla():
    manager, _, _ = _make_manager()
    manager.desactivar()
    assert manager.esta_activo() is False


# Después de desactivar, el canvas secundario debe ser None.
def test_canvas_secundario_none_despues_de_desactivar():
    manager, _, _ = _make_manager()
    manager.activar()
    manager.desactivar()
    assert manager._canvas_secundario is None


# Tests de sincronización


# set_sincronizacion(False) debe desconectar la señal extentsChanged.
def test_set_sincronizacion_false_desconecta():
    manager, iface, canvas_principal = _make_manager()
    manager.activar()
    manager.set_sincronizacion(False)
    assert manager._sincronizado is False


# set_sincronizacion(True) después de False debe reconectar la señal.
def test_set_sincronizacion_true_reconecta():
    manager, iface, canvas_principal = _make_manager()
    manager.activar()
    manager.set_sincronizacion(False)
    manager.set_sincronizacion(True)
    assert manager._sincronizado is True


# set_sincronizacion() antes de activar debe guardar la preferencia.
def test_set_sincronizacion_sin_activar_guarda_preferencia():
    manager, _, _ = _make_manager()
    manager.set_sincronizacion(False)
    assert manager._sincronizado is False


# _on_extent_changed debe copiar el extent del canvas principal al secundario.
def test_on_extent_changed_actualiza_canvas_secundario():
    manager, iface, canvas_principal = _make_manager()
    manager.activar()

    # Simular que el canvas principal tiene un extent específico
    extent_mock = MagicMock()
    canvas_principal.extent.return_value = extent_mock

    # Llamar al callback de sincronización
    manager._on_extent_changed()

    # El canvas secundario debe haber recibido el mismo extent
    manager._canvas_secundario.setExtent.assert_called_with(extent_mock)
    manager._canvas_secundario.refresh.assert_called()


# _on_extent_changed sin canvas secundario no debe lanzar errores.
def test_on_extent_changed_sin_canvas_no_falla():
    manager, _, _ = _make_manager()
    # canvas_secundario es None porque no se activó
    manager._on_extent_changed()


# Tests de get_canvas_secundario


# get_canvas_secundario() debe retornar None si no está activo.
def test_get_canvas_secundario_retorna_none_sin_activar():
    manager, _, _ = _make_manager()
    assert manager.get_canvas_secundario() is None


# get_canvas_secundario() debe retornar el canvas cuando está activo.
def test_get_canvas_secundario_retorna_canvas_activo():
    manager, _, _ = _make_manager()
    manager.activar()
    assert manager.get_canvas_secundario() is not None
