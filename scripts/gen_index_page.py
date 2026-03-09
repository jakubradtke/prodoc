"""Generate index.html for a documents repository from directory structure."""

import sys
from pathlib import Path
from datetime import date
from typing import Iterable, Iterator, NamedTuple, Optional

import yaml

# Head HTML is loaded from index_head.html next to this script.
SCRIPT_DIR = Path(__file__).resolve().parent
HEAD_HTML_PATH = SCRIPT_DIR / "index_head.html"


class DocInfo(NamedTuple):
    html_path: Path
    mmd_path: Optional[Path]
    title: Optional[str]
    classification: Optional[str]


def load_head_html() -> str:
    """Load <head> fragment from external template file."""
    return HEAD_HTML_PATH.read_text(encoding="utf-8").strip()


def find_frontmatter_title(mmd_path: Path) -> tuple[Optional[str], Optional[str]]:
    """Extract title and classification from MMD file YAML frontmatter."""
    text = mmd_path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        return None, None

    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return None, None

    fm_lines = []
    for line in lines[1:]:
        stripped = line.strip()
        if stripped in ("...", "---"):
            break
        fm_lines.append(line)

    if not fm_lines:
        return None, None

    fm_text = "\n".join(fm_lines)
    try:
        data = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return None, None

    title = data.get("title")
    classification = data.get("classification")
    return title, classification


def enrich_with_mmd(
    html_paths: Iterable[str] | Iterable[Path],
    root: Path,
) -> Iterator[DocInfo]:
    """Attach MMD metadata (title, classification) to each HTML path."""
    for html in html_paths:
        rel_html_path = Path(html)
        full_html_path = (
            rel_html_path if rel_html_path.is_absolute() else root / rel_html_path
        )
        mmd_path = full_html_path.with_suffix(".mmd")

        if mmd_path.is_file():
            title, classification = find_frontmatter_title(mmd_path)
        else:
            title, classification = None, None

        yield DocInfo(
            html_path=rel_html_path,
            mmd_path=mmd_path if mmd_path.is_file() else None,
            title=title,
            classification=classification,
        )


def collect_html(dir_path: Path, root: Path) -> Iterator[str]:
    """Yield relative paths to .html files, excluding index.html and /auto/."""
    for path in sorted(dir_path.rglob("*.html")):
        if path.name == "index.html":
            continue
        rel_str = path.relative_to(root).as_posix()
        if "/auto/" in rel_str:
            continue
        yield rel_str


def collect_section(
    header: str, base: Path, root: Path
) -> Optional[tuple[str, list[DocInfo]]]:
    """Build one section (header + list of DocInfo). Returns None if no docs."""
    links = list(collect_html(base, root))
    docs = list(enrich_with_mmd(links, root=root))
    return (header, docs) if docs else None


def gather_sections(root: Path) -> list[tuple[str, list[DocInfo]]]:
    """Gather sections from index_order.txt or a single 'Documents' section."""
    sections: list[tuple[str, list[DocInfo]]] = []
    index_order = root / "index_order.txt"

    if index_order.exists():
        for child in sorted(p for p in root.iterdir() if p.is_dir()):
            section = collect_section(child.name, child, root)
            if section:
                sections.append(section)
    else:
        section = collect_section("Documents", root, root)
        if section:
            sections.append(section)

    return sections


def build_index_html(root: Path, head_html: str) -> str:
    """Build full index.html content."""
    sections = gather_sections(root)
    today_str = date.today().strftime("%B %d, %Y")

    parts = [
        "<!DOCTYPE html>",
        "<html>",
        head_html,
        "<body><div class=\"container\">",
        "<h1>Documents repository</h1>",
        f"<h3>{today_str}</h3>",
        "<div class=columns>",
    ]

    for header, links in sections:
        parts.append(f"<div class=column><h2>{header}</h2>")
        parts.append("<ul>")
        for info in sorted(links, key=lambda i: (i.title is None, i.title or "")):
            text = info.title or info.html_path
            parts.append(f'  <li><a href="{info.html_path}">{text}</a></li>')
        parts.append("</ul></div>")

    parts.extend(["</div></div></body>", "</html>"])
    return "\n".join(parts)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <start path>")
        return 1

    root = Path(sys.argv[1]).resolve()
    head_html = load_head_html()
    html = build_index_html(root, head_html)
    (root / "index.html").write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
