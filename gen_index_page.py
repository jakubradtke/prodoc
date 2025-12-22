import sys
from pathlib import Path
import yaml
from typing import Iterable, Iterator, NamedTuple, Optional

HEAD_HTML ="""
<head>
  <meta charset="utf-8">
  <title>Documents index</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f5f7;
      color: #222;
      line-height: 1.5;
    }
    .container {
      max-width: 800px;
      margin: 40px auto;
      padding: 24px 32px;
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.06);
    }
    h1 {
      margin-top: 0;
      margin-bottom: 0.5em;
    }
    h2 {
      margin-top: 1.5em;
      border-bottom: 1px solid #eee;
      padding-bottom: 0.25em;
      font-size: 1.1rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #555;
    }
    ul {
      list-style-type: disc;
      padding-left: 1.5rem;
      margin: 0.5em 0 0;
    }
    li {
      margin: 0.25em 0;
    }
    a {
      color: #0066cc;
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }
  </style>
</head>
"""

class DocInfo(NamedTuple):
    html_path: Path
    mmd_path: Optional[Path]
    title: Optional[str]
    classification: Optional[str]

def find_frontmatter_title(mmd_path: Path) -> tuple[Optional[str], Optional[str]]:
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
) -> Iterable[DocInfo]:
    for html in html_paths:
        rel_html_path = Path(html)
        full_html_path = rel_html_path if rel_html_path.is_absolute() else root / rel_html_path
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

def collect_html(dir_path: Path, root: Path) -> Iterable[str]:
    for path in sorted(dir_path.rglob("*.html")):
        if path.name == "index.html":
            continue
        rel_str = path.relative_to(root).as_posix()
        if "/auto/" in rel_str:
            continue
        yield rel_str

def collect_section(header: str, base: Path, root: Path) -> tuple[str, list[DocInfo]] | None:
    links = list(collect_html(base, root))
    docs = list(enrich_with_mmd(links, root=root))
    return (header, docs) if docs else None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <start path>")
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    index_order = root / "index_order.txt"

    sections: list[tuple[str, list[DocInfo]]] = []

    if index_order.exists():
        for child in sorted(p for p in root.iterdir() if p.is_dir()):
            section = collect_section(child.name, child, root)
            if section:
                sections.append(section)
    else:
        section = collect_section("Documents", root, root)
        if section:
            sections.append(section)

    parts: list[str] = [
        "<!DOCTYPE html>",
        "<html>",
        HEAD_HTML,
        "<body><div class=\"container\">",
        "<h1>Documents index</h1>",
    ]

    for header, links in sections:
        parts.append(f"<h2>{header}</h2>")
        parts.append("<ul>")
        for info in sorted(links, key=lambda i: (i.title is None, i.title or "")):
            text = info.title or info.html_path
            parts.append(f'  <li><a href="{info.html_path}">{text}</a></li>')
        parts.append("</ul>")

    parts.extend(["</div></body>", "</html>"])
    (root / "index.html").write_text("\n".join(parts), encoding="utf-8")
