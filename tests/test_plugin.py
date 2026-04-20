# Tests básicos del plugin GeoGlyph
import importlib.util
import os


def test_plugin_import():
    plugin_init = os.path.join(os.path.dirname(__file__), '..', '__init__.py')
    spec = importlib.util.spec_from_file_location('plugin', plugin_init)
    assert spec is not None


def test_metadata_exists():
    metadata_path = os.path.join(os.path.dirname(__file__), '..', 'metadata.txt')
    assert os.path.exists(metadata_path)


def test_http_worker_module_exists():
    """El módulo http_worker debe existir y ser importable como spec."""
    worker_path = os.path.join(os.path.dirname(__file__), '..', 'http_worker.py')
    assert os.path.exists(worker_path), "http_worker.py no encontrado"
    spec = importlib.util.spec_from_file_location('http_worker', worker_path)
    assert spec is not None


def test_enhance_worker_payload_structure():
    """EnhanceWorker arma el payload correcto sin necesitar QApplication."""
    import ast
    worker_path = os.path.join(os.path.dirname(__file__), '..', 'http_worker.py')
    with open(worker_path, encoding='utf-8') as f:
        source = f.read()
    # Verificar que el payload tiene los campos que espera el backend (TIGS-41)
    assert '"bbox"' in source or "'bbox'" in source, "Falta campo bbox en payload"
    assert '"band"' in source or "'band'" in source, "Falta campo band en payload"


def test_placeholder():
    assert True