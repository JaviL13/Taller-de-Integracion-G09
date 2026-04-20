# Tests basicos del plugin GeoGlyph
import importlib.util
import os


def test_plugin_import():
        plugin_init = os.path.join(os.path.dirname(__file__), '..', '__init__.py')
        spec = importlib.util.spec_from_file_location('plugin', plugin_init)
        assert spec is not None


def test_metadata_exists():
        metadata_path = os.path.join(os.path.dirname(__file__), '..', 'metadata.txt')
        assert os.path.exists(metadata_path)


def test_placeholder():
        assert True
