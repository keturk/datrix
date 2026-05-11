"""Unit tests for Ollama integration."""

from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from review import call_ollama, check_ollama_reachable


def test_call_ollama_success(monkeypatch) -> None:
    """Test successful Ollama API call."""
    # Mock urllib.request.urlopen
    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self) -> bytes:
            return json.dumps(
                {"message": {"content": '{"verdict": "pass"}'}}
            ).encode("utf-8")

    def mock_urlopen(*args, **kwargs):
        return MockResponse()

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    response = call_ollama("test prompt", "http://localhost:11434", "qwen2.5-coder:14b")

    assert response is not None
    assert "verdict" in response


def test_call_ollama_connection_error(monkeypatch) -> None:
    """Test Ollama API call with connection error."""
    import urllib.request
    import urllib.error

    def mock_urlopen(*args, **kwargs):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    response = call_ollama("test prompt", "http://localhost:11434", "qwen2.5-coder:14b")

    assert response is None


def test_call_ollama_timeout(monkeypatch) -> None:
    """Test Ollama API call timeout."""
    import urllib.request

    def mock_urlopen(*args, **kwargs):
        raise TimeoutError("Timeout")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    response = call_ollama(
        "test prompt", "http://localhost:11434", "qwen2.5-coder:14b", timeout=1
    )

    assert response is None


def test_check_ollama_reachable_success(monkeypatch) -> None:
    """Test Ollama reachability check when server is up."""

    class MockResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def mock_urlopen(*args, **kwargs):
        return MockResponse()

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    config = {"tier1": {"endpoint": "http://localhost:11434"}}
    assert check_ollama_reachable(config)


def test_check_ollama_reachable_failure(monkeypatch) -> None:
    """Test Ollama reachability check when server is down."""
    import urllib.request
    import urllib.error

    def mock_urlopen(*args, **kwargs):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    config = {"tier1": {"endpoint": "http://localhost:11434"}}
    assert not check_ollama_reachable(config)
