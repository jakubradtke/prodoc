"""
Generate a single-file index.html for a documents repository from a JSON description.

Usage: build_index.py [index.json] [-o OUTPUT]

JSON format (paths are relative to the JSON file):
{
  "title": "Documents repository",       # optional
  "output": "index.html",                # optional
  "filter": true,                        # optional, adds a search box
  "show_dates": true,                    # optional, shows last change date per document
  "date_source": "git",                  # optional: "git" (last commit of source + inserted
                                         #   files, falls back to "file") or "file" (HTML mtime)
  "max_columns_per_row": 3,              # optional, grid auto-fits when omitted
  "columns": [
    {
      "title": "Architecture",
      "sort": "title",                   # optional: "title" or "none" (JSON order)
      "documents": [
        "path/to/doc.md",                # link goes to path/to/doc.html
        {"path": "path/to/other.mmd", "title": "Explicit title"},
        "path/**/*.md"                   # globs: *, ?, ** (recursive)
      ]
    }
  ]
}
"""

import os
import re
import io
import sys
import cgi
import json
import glob
import time
import urllib
import argparse
import subprocess

import yaml

import util

_thisdir = os.path.dirname(os.path.abspath(__file__))
CSS_FILE = os.path.join(_thisdir, "..", "stylesheets", "index.css")
JS_FILE = os.path.join(_thisdir, "..", "frontend", "index.js")
SOURCE_EXTS = (".mmd", ".md")
# Same syntax as the INSERT_FILE token in mmd2doc.py: [file.md], [!file.md], [html:file.md]
INCLUDE_RE = re.compile(r"(?m)^[ \t]*\[(?:(docx|html|pdf):)?(!?[\w\-\*\? \t/\\.]+\.mm?d)\]")


def console(message):
    # Python 2 print of non-ASCII unicode fails on pipes; encode explicitly
    if isinstance(message, unicode):
        message = message.encode(sys.getfilesystemencoding() or "utf-8", "replace")
    return message


def fail(message):
    util.error(console(u"ERROR: %s" % message))
    sys.exit(1)


def warn(message):
    print console(u"WARNING: %s" % message)


def read_text(fname):
    with io.open(fname, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def load_config(fname):
    if not os.path.isfile(fname):
        fail("Index description not found: %s" % fname)
    try:
        cfg = json.loads(read_text(fname))
    except ValueError as e:
        fail("Invalid JSON in %s: %s" % (fname, e))
    if not isinstance(cfg, dict) or not isinstance(cfg.get("columns"), list) or not cfg["columns"]:
        fail("%s: 'columns' must be a non-empty list" % fname)
    if cfg.get("date_source", "git") not in ("git", "file"):
        fail("%s: invalid 'date_source' (use 'git' or 'file')" % fname)
    for i, col in enumerate(cfg["columns"]):
        if not isinstance(col, dict) or not col.get("title"):
            fail("%s: column #%d has no 'title'" % (fname, i + 1))
        if not isinstance(col.get("documents"), list):
            fail("%s: column '%s' has no 'documents' list" % (fname, col["title"]))
        if col.get("sort", "none") not in ("none", "title"):
            fail("%s: column '%s' has invalid 'sort' (use 'title' or 'none')" % (fname, col["title"]))
    return cfg


def glob_to_regex(pattern):
    """Translate a glob with *, ? and ** into a regex matched against '/'-separated paths."""
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z", re.IGNORECASE)


def expand_glob(root, pattern):
    """Return sorted files under root matching pattern; skips '_' chapters and auto/ dirs."""
    parts = pattern.split("/")
    fixed = []
    for part in parts:
        if "*" in part or "?" in part:
            break
        fixed.append(part)
    walk_root = os.path.join(root, *fixed) if fixed else root
    regex = glob_to_regex(pattern)
    matches = []
    for dirpath, dirnames, filenames in os.walk(walk_root):
        dirnames[:] = [d for d in dirnames if d.lower() != "auto"]
        for fn in filenames:
            if fn.startswith("_"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if regex.match(rel):
                matches.append(full)
    return sorted(matches)


def find_source(fname):
    """Map an entry path to (source_or_None, html)."""
    base, ext = os.path.splitext(fname)
    if ext.lower() == ".html":
        for src_ext in SOURCE_EXTS:
            if os.path.isfile(base + src_ext):
                return base + src_ext, fname
        return None, fname
    return fname, util.replace_ext(fname, ".html")


def resolve_title(src, html):
    """Title from YAML front matter, then first '# ' heading, then file name."""
    if src and os.path.isfile(src):
        text = read_text(src)
        # Leading blank lines before the front matter are accepted by pandoc too
        m = re.match(r"\s*---[ \t]*\r?\n(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", text, re.DOTALL)
        if m:
            try:
                data = yaml.safe_load(m.group(1))
            except yaml.YAMLError:
                data = None
            if isinstance(data, dict) and data.get("title"):
                return unicode(data["title"]).strip()
            text = text[m.end():]
        m = re.search(r"(?m)^#[ \t]+(.+?)[ \t#]*$", text)
        if m:
            return m.group(1)
    return os.path.splitext(os.path.basename(html))[0]


def make_href(html, out_dir):
    rel = os.path.relpath(html, out_dir).replace("\\", "/")
    return urllib.quote(rel.encode("utf-8"), safe="/")


def collect_sources(src, found):
    """Collect src and, recursively, files it inserts via [file.md] tags (html builds only)."""
    key = os.path.normcase(os.path.abspath(src))
    if key in found or not os.path.isfile(src):
        return
    found[key] = src
    dirname = os.path.dirname(src)
    for m in INCLUDE_RE.finditer(read_text(src)):
        fmt, inner = m.group(1), m.group(2).strip()
        if fmt and fmt != "html":
            continue
        pattern = os.path.join(dirname, inner.lstrip("!").replace("/", os.sep))
        for fname in glob.glob(pattern):
            collect_sources(fname, found)


def git_date(files):
    """Date (YYYY-MM-DD) of the last commit touching any of files, or None."""
    cwd = os.path.dirname(files[0])
    fsenc = sys.getfilesystemencoding()
    cmd = ["git", "log", "-1", "--format=%cd", "--date=short", "--"] + \
        [os.path.relpath(f, cwd) for f in files]
    try:
        out = subprocess.check_output([c.encode(fsenc) for c in cmd], cwd=cwd.encode(fsenc),
                                      stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError):
        return None
    out = out.strip()
    return out if re.match(r"\d{4}-\d\d-\d\d$", out) else None


def document_date(src, html, date_source):
    """Last change date: git history of the source and its inserted files, else HTML mtime."""
    if date_source == "git" and src:
        found = {}
        collect_sources(src, found)
        if found:
            date = git_date(sorted(found.values()))
            if date:
                return date
    return time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(html)))


def collect_documents(col, root, out_file, date_source):
    docs = []
    for entry in col["documents"]:
        if isinstance(entry, dict):
            path, title = entry.get("path"), entry.get("title")
        else:
            path, title = entry, None
        if not path:
            fail("column '%s': document entry without 'path'" % col["title"])
        path = path.replace("\\", "/")
        if "*" in path or "?" in path:
            files = expand_glob(root, path)
            if not files:
                warn("column '%s': pattern '%s' matched no files" % (col["title"], path))
        else:
            files = [os.path.join(root, *path.split("/"))]
        for fname in files:
            src, html = find_source(os.path.normpath(fname))
            if os.path.normcase(html) == os.path.normcase(out_file):
                continue
            if not os.path.isfile(html):
                warn("column '%s': %s not built, skipped" % (col["title"], os.path.relpath(html, root)))
                continue
            docs.append({
                "title": title or resolve_title(src, html),
                "html": html,
                "date": document_date(src, html, date_source),
            })
    if col.get("sort") == "title":
        docs.sort(key=lambda d: d["title"].lower())
    return docs


def render(cfg, columns, out_dir):
    esc = lambda s: cgi.escape(s, True)
    title = esc(cfg.get("title", "Documents repository"))
    use_filter = cfg.get("filter", True)
    show_dates = cfg.get("show_dates", True)
    max_cols = cfg.get("max_columns_per_row")

    out = [
        u'<!DOCTYPE html>',
        u'<html lang="en">',
        u'<head>',
        u'<meta charset="utf-8">',
        u'<meta name="viewport" content="width=device-width,initial-scale=1">',
        u'<title>%s</title>' % title,
        u'<style>%s</style>' % read_text(CSS_FILE).strip(),
        u'</head>',
        u'<body>',
        u'<header><h1>%s</h1>' % title,
    ]
    if use_filter:
        out.append(u'<input id="filter" type="search" placeholder="Filter documents (press /)" aria-label="Filter documents">')
    out.append(u'</header>')
    out.append(u'<main style="--max-cols:%d">' % int(max_cols) if max_cols else u'<main>')
    for col, docs in columns:
        out.append(u'<section><h2>%s</h2><ul>' % esc(col["title"]))
        for d in docs:
            item = u'<li><a href="%s">%s</a>' % (make_href(d["html"], out_dir), esc(d["title"]))
            if show_dates:
                item += u'<time>%s</time>' % d["date"]
            out.append(item + u'</li>')
        out.append(u'</ul></section>')
    out.append(u'</main>')
    out.append(u'<footer>Generated %s &middot; prodoc %s</footer>' % (time.strftime("%Y-%m-%d"), util.get_toolver()))
    if use_filter:
        out.append(u'<script>%s</script>' % read_text(JS_FILE).strip())
    out.append(u'</body>')
    out.append(u'</html>')
    return u"\n".join(out) + u"\n"


def main():
    parser = argparse.ArgumentParser(description="Generate index.html from a JSON description")
    parser.add_argument("index_json", nargs="?", default="index.json", help="JSON description (default: index.json)")
    parser.add_argument("-o", "--output", help="Output HTML file (overrides 'output' from JSON)")
    opts = parser.parse_args()

    # Work with unicode paths so non-ASCII file names from JSON and os.walk mix safely
    fsenc = sys.getfilesystemencoding()
    json_file = os.path.abspath(opts.index_json.decode(fsenc))
    cfg = load_config(json_file)
    root = os.path.dirname(json_file)
    out_file = os.path.abspath(opts.output.decode(fsenc)) if opts.output else \
        os.path.normpath(os.path.join(root, cfg.get("output", "index.html")))
    out_dir = os.path.dirname(out_file)

    # Skip git lookups when dates are not displayed
    date_source = cfg.get("date_source", "git") if cfg.get("show_dates", True) else "file"
    columns = []
    for col in cfg["columns"]:
        docs = collect_documents(col, root, out_file, date_source)
        if docs:
            columns.append((col, docs))
        else:
            warn("column '%s' has no documents, skipped" % col["title"])

    with io.open(out_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(cfg, columns, out_dir))
    print console(u"Generated %s (%d documents)" % (out_file, sum(len(d) for _, d in columns)))


if __name__ == "__main__":
    main()
