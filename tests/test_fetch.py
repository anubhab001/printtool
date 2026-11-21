"""Links and attachments: Names are safe, and the buffer is used."""

from printtool.core import fetch


def test_names_stay_inside() -> None:
    assert fetch._name_for("https://x/a/..%2F..%2Fevil.pdf") == "evil.pdf"
    assert fetch._name_for("https://x/") == "download"


def test_virtual_attachment_saved(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetch, "_buffer", tmp_path)
    p = fetch.save_virtual("report.pdf", b"%PDF-1.4")
    assert p.parent == tmp_path and p.read_bytes() == b"%PDF-1.4"
    assert fetch.save_virtual("report.pdf", b"x").name == "report (2).pdf"


def test_file_url_is_local() -> None:
    kind, items = fetch.look("file:///C:/temp/a.pdf", {".pdf"})
    assert kind == "local" and items[0].endswith("a.pdf")
