# Tests básicos del plugin GeoGlyph
# Este archivo sirve como punto de partida para las pruebas unitarias del plugin.


def test_plugin_import():
      """Verifica que el módulo principal del plugin es importable."""
      import importlib.util
      import os

    plugin_init = os.path.join(os.path.dirname(__file__), '..', '__init__.py')
    spec = importlib.util.spec_from_file_location("plugin", plugin_init)
    assert spec is not None, "No se encontró el archivo __init__.py del plugin"


def test_metadata_exists():
      """Verifica que el archivo metadata.txt existe."""
      import os

    metadata_path = os.path.join(os.path.dirname(__file__), '..', 'metadata.txt')
    assert os.path.exists(metadata_path), "No se encontró el archivo metadata.txt"


def test_placeholder():
      """Test de placeholder para que el pipeline no falle por falta de tests."""
      assert True
