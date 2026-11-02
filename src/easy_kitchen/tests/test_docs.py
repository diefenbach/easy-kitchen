from pathlib import Path

from sphinx.cmd.build import build_main

DOCS = Path(__file__).resolve().parents[3] / "docs"


def test_sphinx_docs_build(tmp_path):
    assert build_main(["-W", "-b", "html", str(DOCS), str(tmp_path)]) == 0
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "mcp.html").exists()
