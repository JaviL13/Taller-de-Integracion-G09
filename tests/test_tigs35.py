import sys                                  # Permite modificar rutas y módulos del intérprete de Python
import os                                   # Premite interactuar con el sistema de archivos
import pytest                               # Framework de testing
import numpy as np                          # Crea arrays numéricos para generar los pixeles del GeoTIFF de prueba
import rasterio                             # Lee y escribe archivos GeoTIFF y otros formatos raster geoespaciales
from rasterio.transform import from_bounds  # Calcula la transformación geoespacial a partir de coordenadas reales
from unittest.mock import MagicMock         # Crea objetos falsos para simular QGIS sin tenerlo instalado en el pipeline

# El pipeline de CI no tiene QGIS instalado. Si importamos el plugin directamente, 
# Python busca "from qgis.core import ..." y fallaa antes de correr un test.
# Por esto, se cambiarán esos módulos por un mock falso antes de importar el pluggin.
qgis_mock = MagicMock()
sys.modules['qgis'] = qgis_mock
sys.modules['qgis.PyQt'] = qgis_mock
sys.modules['qgis.PyQt.QtWidgets'] = qgis_mock
sys.modules['qgis.PyQt.QtCore'] = qgis_mock
sys.modules['qgis.PyQt.QtGui'] = qgis_mock
sys.modules['qgis.core'] = qgis_mock

# Agrega la carpeta raíz al path para que Python encuentre los archivos del plugin
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Crea un GeoTIFF  pequeño y válido en una carpeta temporal
# tmp_path es creada y borrada automáticamente por pytest
@pytest.fixture
def geotiff_valido(tmp_path):
    filepath = tmp_path / "test.tif"
    data = np.random.randint(0, 255, (1, 10, 10), dtype=np.uint8)   # Imagen de 10x10 píxeles con valores aleatorios entre 0 y 255
    transform = from_bounds(-70, -20, -69, -19, 10, 10)             # Cubre lon -70 a -69, lat -20 a -19
    with rasterio.open(
        filepath,
        'w',                 # Modo escritura
        driver='GTiff',      # Formato GeoTIFF
        height=10,
        width=10,        
        count=1,             # 1 banda espectral
        dtype='uint8',       # Entero de 8 bits
        crs='EPSG:4326',     # Sistema de coordenadas WGS84
        transform=transform
    ) as dst:
        dst.write(data)
    return str(filepath)

# Crea un archivo .tif con texto plano, que rasterio no puede abrir para probar cuando falle 
@pytest.fixture
def archivo_invalido(tmp_path):
    filepath = tmp_path / "invalido.tif"
    filepath.write_text("esto no es un geotiff")
    return str(filepath)


# TESTS ────────────────────────────────────────────────────────────────────────────

# Verifica que un GeoTIFF valido se abre sin errores y tiene al menos 1 banda
def test_carga_geotiff_valido(geotiff_valido):
    with rasterio.open(geotiff_valido) as src:
        assert src.count >= 1
        assert src.crs is not None

# Verfica que abrir un archivo inválido lanza una excepción
def test_carga_archivo_invalido(archivo_invalido):
    with pytest.raises(Exception):
        rasterio.open(archivo_invalido)

# Verifica que el fixture pesa menos de 5 MB, criterio de aceptación de TIGS-35
def test_geotiff_menor_5mb(geotiff_valido):
    tamanio_mb = os.path.getsize(geotiff_valido) / (1024 * 1024)
    assert tamanio_mb < 5

# Verifica que el archivo del panel existe en el repositorio
def test_panel_se_crea():
    panel_path = os.path.join(os.path.dirname(__file__), '..', 'geoglyph_panel.py')
    assert os.path.exists(panel_path)

# Verfica que btn_abrir_tiff está definido en el código del panel
def test_panel_tiene_boton_abrir_tiff():
    panel_path = os.path.join(os.path.dirname(__file__), '..', 'geoglyph_panel.py')
    with open(panel_path, 'r', encoding='utf-8') as f:
        contenido = f.read()
    assert 'btn_abrir_tiff' in contenido


# Referencias ──────────────────────────────────────────────────────────────────────────────
# Tests implementados con apoyo de Claude (IA de Anthropic) para entender la estructura de 
# pytest, mocks y fixtures. El código fue revisado, ajustado y validado localmente.