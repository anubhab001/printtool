"""Printable files inside a zip (including zips nested inside zips),
tracked without extracting anything until a specific member is actually
needed for printing. SumatraPDF/CUPS still need a real file on disk at
that point, so extraction happens then, into a temporary folder.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


def is_archive(path: Path) -> bool:
    return path.suffix.lower() == ".zip"


@dataclass
class ArchiveNode:
    """One entry in a zip's tree: either a printable file (a leaf) or a
    nested zip (its own node, with its own children). `chain` is the
    member-name path from the outermost zip down to this node, used to
    extract it later without having to re-walk the tree."""

    name: str
    chain: tuple[str, ...]
    is_zip: bool
    children: list["ArchiveNode"] = field(default_factory=list)


def _walk(zf: zipfile.ZipFile, prefix: tuple[str, ...], extensions: set[str]) -> list[ArchiveNode]:
    allowed = {e.lower().lstrip(".") for e in extensions}
    nodes = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        chain = (*prefix, info.filename)
        display_name = Path(info.filename).name
        if info.filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(zf.read(info))) as inner:
                children = _walk(inner, chain, extensions)
            if children:
                nodes.append(ArchiveNode(display_name, chain, is_zip=True, children=children))
        elif Path(info.filename).suffix.lower().lstrip(".") in allowed:
            nodes.append(ArchiveNode(display_name, chain, is_zip=False))
    return nodes


def build_tree(zip_path: Path, extensions: set[str]) -> ArchiveNode:
    """The whole printable tree inside `zip_path`, one ArchiveNode per
    member (recursing into any zip nested inside it); a nested zip with
    no printable content anywhere inside it is left out entirely."""
    with zipfile.ZipFile(zip_path) as zf:
        children = _walk(zf, (), extensions)
    return ArchiveNode(zip_path.name, (), is_zip=True, children=children)


def iter_leaves(node: ArchiveNode) -> list[tuple[str, ...]]:
    """Every printable-file chain under `node`, depth-first."""
    chains = []
    for child in node.children:
        if child.is_zip:
            chains += iter_leaves(child)
        else:
            chains.append(child.chain)
    return chains


def extract_all(zip_path: Path, extensions: set[str]) -> list[Path]:
    """Every printable file anywhere in `zip_path` (nested zips included),
    extracted up front; for the CLI, which has no interactive tree to
    pick from the way the GUI queue does."""
    tree = build_tree(zip_path, extensions)
    return [extract_leaf(zip_path, chain) for chain in iter_leaves(tree)]


def extract_leaf(zip_path: Path, chain: tuple[str, ...]) -> Path:
    """Extract the member named by `chain` (walking through any zips
    nested along the way, entirely in memory until the last hop) to a
    fresh temporary folder, and return its path there."""
    dest = Path(tempfile.mkdtemp(prefix="printtool-zip-")).resolve()
    with zipfile.ZipFile(zip_path) as zf:
        return _extract_from(zf, chain, dest)


def read_leaf_bytes(zip_path: Path, chain: tuple[str, ...]) -> bytes:
    """The member named by `chain`'s raw bytes, walking through any zips
    nested along the way in memory, without writing anything to disk --
    enough to read a PDF's page count ahead of actually printing it."""
    with zipfile.ZipFile(zip_path) as zf:
        return _read_from(zf, chain)


def _read_from(zf: zipfile.ZipFile, chain: tuple[str, ...]) -> bytes:
    data = zf.read(chain[0])
    return data if len(chain) == 1 else _read_from(zipfile.ZipFile(io.BytesIO(data)), chain[1:])


def _extract_from(zf: zipfile.ZipFile, chain: tuple[str, ...], dest: Path) -> Path:
    name = chain[0]
    if len(chain) == 1:
        target = (dest / name).resolve()
        if dest != target and dest not in target.parents:
            raise ValueError(f"unsafe member path: {name}")
        zf.extract(name, dest)
        return dest / name
    with zipfile.ZipFile(io.BytesIO(zf.read(name))) as inner:
        return _extract_from(inner, chain[1:], dest)
