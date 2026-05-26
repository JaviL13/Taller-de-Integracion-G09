# TIGS 93: Integrar QGIS en el pipeline de CI 

# Este archivo contiene un test básico para verificar que el entorno QGIS
# funciona correctamente dentro del pipeline de CI (GitHub Actions).

# La TIGS-93 agrega un stage nuevo al pipeline que corre dentro de un contenedor Docker que
# sí tiene QGIS. Este archivo verifica que ese contenedor funciona.

# -*- coding: utf-8 -*-

def test_qgis_application_starts(qgis_app):     
    
    # qgis_app es un fixture que provee pytest-qgis automáticamente. Se encarga de 
    # inicializar QGIS antes del test y apagarlo al terminar,
    from qgis.core import QgsApplication

    assert qgis_app is not None

    # Verificamos que podemos obtener la versión de QGIS
    # Si QGIS no estuviera instalado, esto fallaría con un error de import
    assert QgsApplication.version() is not None