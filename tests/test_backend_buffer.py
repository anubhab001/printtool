from pathlib import Path

from printtool.core import backend
from printtool.core.models import PrintSettings


class _FakeImpl:
    """Stands in for the real OS backend module; records the path it was
    actually asked to print, so the test can tell whether a buffer copy
    (not the original) was used."""

    def __init__(self):
        self.printed_path: Path | None = None

    def print_file(self, path, settings):
        self.printed_path = Path(path)
        assert self.printed_path.is_file()
        return True, "printed"


def test_buffer_copy_prints_a_copy_and_leaves_original(tmp_path, monkeypatch):
    fake = _FakeImpl()
    monkeypatch.setattr(backend, "_backend", lambda: fake)

    original = tmp_path / "doc.pdf"
    original.write_text("content")

    result = backend.print_file(original, PrintSettings(buffer_copy=True))

    assert result.success
    assert fake.printed_path != original
    assert fake.printed_path.name == "doc.pdf"
    assert not fake.printed_path.exists()  # temp dir cleaned up afterwards
    assert original.exists()  # original untouched


def test_delete_after_print_removes_original_on_success(tmp_path, monkeypatch):
    fake = _FakeImpl()
    monkeypatch.setattr(backend, "_backend", lambda: fake)

    original = tmp_path / "doc.pdf"
    original.write_text("content")

    result = backend.print_file(original, PrintSettings(delete_after_print=True))

    assert result.success
    assert not original.exists()


def test_delete_after_print_keeps_original_on_failure(tmp_path, monkeypatch):
    class _FailingImpl:
        def print_file(self, path, settings):
            return False, "printer offline"

    monkeypatch.setattr(backend, "_backend", lambda: _FailingImpl())

    original = tmp_path / "doc.pdf"
    original.write_text("content")

    result = backend.print_file(original, PrintSettings(delete_after_print=True))

    assert not result.success
    assert original.exists()
