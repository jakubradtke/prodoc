import os
import sys
from pathlib import Path

def collect_html(dir_path: Path, root: Path):
    for path in sorted(dir_path.rglob("*.html")):
        if path.name == "index.html":
            continue
        rel = path.relative_to(root)
        rel_str = rel.as_posix()
        if "/auto/" in rel_str:
            continue
        yield rel_str

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <start path>")
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    index_order = root / "index_order.txt"

    sections = []

    if index_order.exists():
        for child in sorted(p for p in root.iterdir() if p.is_dir()):
            header = child.name
            links = list(collect_html(child, root))
            if links:
                sections.append((header, links))
    else:
        links = list(collect_html(root, root))
        if links:
            sections.append(("Documents", links))

    parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head><meta charset=\"utf-8\"><title>Documents index</title></head>",
        "<body>",
        "<h1>Documents index</h1>",
    ]

    for header, links in sections:
        parts.append(f"<h2>{header}</h2>")
        parts.append("<ul>")
        for rel_str in links:
            filename = Path(rel_str).stem
            parts.append(f'  <li><a href="{rel_str}">{filename}</a></li>')
        parts.append("</ul>")

    parts.extend(["</body>", "</html>"])
    html = os.linesep.join(parts)

    (root / "index.html").write_text(html, encoding="utf-8")

if __name__ == "__main__":
    main()
