# TIGS 93: Integrar QGIS en el pipeline de CI

# Este archivo es leído automáticamente por pytest antes de correr cualquier test.
# Su trabajo es clasificar los tests en dos grupos: los "qgis" y los "pure_python" (no necesitan QGIS).
# Los primeros corren en el stage test-qgis del pipeline (dentro de Docker con QGIS) y
# los segundos corren en el stage test normal (sin QGIS).

# -*- coding: utf-8 -*-

import pytest


def pytest_collection_modifyitems(config, items):

    # Esta función es llamada por pytest después de encontrar todos los tests.
    # Le pone etiqueta "qgis" a los tests que necesitan QGIS, y "pure_python" a los que no.

    # pytest-qgis tiene fixtures especiales, que son las a continuación.
    # Si un test usa alguno de esos fixtures, significa que necesita QGIS.

    qgis_fixtures = {
        "qgis_app",
        "qgis_new_project",
        "qgis_iface",
        "qgis_canvas",
        "qgis_bot",
    }

    for item in items:  # item.fixturenames es la lista de fixtures que usa ese test
        if qgis_fixtures.intersection(item.fixturenames):  # Veo si hay algún fixture de QGIS
            item.add_marker(pytest.mark.qgis)  # Si la hay, marco con "qgis"
        else:
            item.add_marker(pytest.mark.pure_python)  # Si no, marco con "pure_python"
