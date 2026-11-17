import zipfile
from pathlib import Path

from printtool.core.archive import build_tree, extract_all, extract_leaf, is_archive, iter_leaves


def _make_zip(tmp_path):
    zip_path = tmp_path / "deck.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("report.pdf", "pdf-bytes")
        zf.writestr("notes.txt", "text-bytes")
        zf.writestr("sub/invoice.pdf", "pdf-bytes-2")
    return zip_path


def _make_nested_zip(tmp_path):
    inner = tmp_path / "_inner.zip"
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("inner.pdf", "inner-bytes")
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        zf.writestr("outer.pdf", "outer-bytes")
        zf.write(inner, "nested.zip")
    inner.unlink()
    return outer


def test_is_archive():
    assert is_archive(Path("deck.zip"))
    assert not is_archive(Path("deck.pdf"))


def test_build_tree_filters_by_extension(tmp_path):
    zip_path = _make_zip(tmp_path)
    tree = build_tree(zip_path, {"pdf"})
    names = sorted(c.name for c in tree.children)
    assert names == ["invoice.pdf", "report.pdf"]


def test_build_tree_advanced_extension(tmp_path):
    zip_path = _make_zip(tmp_path)
    tree = build_tree(zip_path, {"pdf", "txt"})
    names = {c.name for c in tree.children}
    assert "notes.txt" in names


def test_build_tree_descends_into_nested_zip(tmp_path):
    zip_path = _make_nested_zip(tmp_path)
    tree = build_tree(zip_path, {"pdf"})
    top_names = {c.name for c in tree.children}
    assert "outer.pdf" in top_names
    nested = next(c for c in tree.children if c.is_zip)
    assert nested.name == "nested.zip"
    assert [g.name for g in nested.children] == ["inner.pdf"]


def test_iter_leaves_flattens_nested_tree(tmp_path):
    zip_path = _make_nested_zip(tmp_path)
    tree = build_tree(zip_path, {"pdf"})
    chains = iter_leaves(tree)
    assert ("outer.pdf",) in chains
    assert ("nested.zip", "inner.pdf") in chains


def test_extract_leaf_top_level(tmp_path):
    zip_path = _make_zip(tmp_path)
    extracted = extract_leaf(zip_path, ("report.pdf",))
    assert extracted.is_file()
    assert extracted.read_text() == "pdf-bytes"


def test_extract_leaf_nested(tmp_path):
    zip_path = _make_nested_zip(tmp_path)
    extracted = extract_leaf(zip_path, ("nested.zip", "inner.pdf"))
    assert extracted.is_file()
    assert extracted.read_text() == "inner-bytes"


def test_extract_leaf_rejects_zip_slip(tmp_path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../escape.pdf", "x")
    try:
        extract_leaf(zip_path, ("../../escape.pdf",))
        assert False, "expected a rejection"
    except ValueError:
        pass


def test_extract_all(tmp_path):
    zip_path = _make_nested_zip(tmp_path)
    extracted = extract_all(zip_path, {"pdf"})
    assert len(extracted) == 2
    assert all(p.is_file() for p in extracted)
