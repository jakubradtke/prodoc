"""
Generate a single-file index.html for a documents repository from a JSON description.

Usage: build_index.py [index.json] [-o OUTPUT]

JSON format (paths are relative to the JSON file):
{
  "title": "Documents repository",       # optional
  "output": "index.html",                # optional
  "filter": true,                        # optional, adds a search box
  "show_dates": true,                    # optional, shows last change date per document
  "mark_new": true,                      # optional, "new" badge for recently changed documents
  "new_days": 2,                         # optional, "new" = changed today or in the last N-1 days
  "recent": 8,                           # optional, size of the "Recently updated" list, 0 = off
  "show_formats": true,                  # optional, small pdf/docx links when those files exist
  "update_every_min": 30,                # optional, footer note "Updated every N minutes" (default 30, 0 = off)
  "show_repo_commit": true,              # optional, footer shows branch/commit of the documents repo
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
    """Translate a glob with *, ? and ** into a regex matched against '/'-separated paths.
    A trailing .md or .mmd matches both source extensions."""
    tail = r"\Z"
    for src_ext in SOURCE_EXTS:
        if pattern.lower().endswith(src_ext):
            pattern, tail = pattern[:-len(src_ext)], r"\.m?md\Z"
            break
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
    return re.compile(out + tail, re.IGNORECASE)


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
    """Map an entry path to (source_or_None, html). A missing .md/.mmd source is
    looked up under the other source extension, so the git date is still found."""
    base, ext = os.path.splitext(fname)
    html = base + ".html"
    if ext.lower() not in SOURCE_EXTS + (".html",):
        return fname, util.replace_ext(fname, ".html")
    if ext.lower() in SOURCE_EXTS and os.path.isfile(fname):
        return fname, html
    for src_ext in SOURCE_EXTS:
        if os.path.isfile(base + src_ext):
            return base + src_ext, html
    return None, html


def resolve_title(src, html):
    """Title from YAML front matter, then first '# ' heading, then file name."""
    title = None
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
                title = unicode(data["title"]).strip()
            text = text[m.end():]
        if not title:
            m = re.search(r"(?m)^#[ \t]+(.+?)[ \t#]*$", text)
            if m:
                title = m.group(1)
    return title or os.path.splitext(os.path.basename(html))[0]


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


GIT_CANDIDATES = [
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Tools\cmder\vendor\git-for-windows\cmd\git.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Git", "cmd", "git.exe"),
]
_git = {"exe": None, "warned": False}


def git_exe():
    """git executable: PRODOC_GIT, then PATH, then common install folders."""
    if _git["exe"] is None:
        found = os.environ.get("PRODOC_GIT") or ""
        if not os.path.isfile(found):
            found = ""
            for d in os.environ.get("PATH", "").split(os.pathsep):
                cand = os.path.join(d.strip('"'), "git.exe")
                if os.path.isfile(cand):
                    found = cand
                    break
        if not found:
            found = next((c for c in GIT_CANDIDATES if os.path.isfile(c)), "")
        _git["exe"] = found
    return _git["exe"]


def git_out(cwd, *args):
    """stdout of a git command run in cwd (unicode), or None on failure.
    The first failure is reported, because dates then fall back to the HTML file time."""
    fsenc = sys.getfilesystemencoding()
    exe = git_exe()
    if not exe:
        if not _git["warned"]:
            warn(u"git not found (set PRODOC_GIT or add git to PATH): dates use HTML file time, no NEW badges")
            _git["warned"] = True
        return None
    cmd = [exe] + list(args)
    try:
        out = subprocess.check_output([c.encode(fsenc) if isinstance(c, unicode) else c for c in cmd],
                                      cwd=cwd.encode(fsenc), stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as e:
        if not _git["warned"]:
            detail = getattr(e, "output", None) or str(e)
            if isinstance(detail, str):
                detail = detail.decode("utf-8", "replace")
            warn(u"git failed in %s: %s" % (cwd, detail.strip().splitlines()[0] if detail.strip() else e))
            _git["warned"] = True
        return None
    return out.decode("utf-8", "replace").strip()


def git_last_commit(files):
    """(timestamp, author, subject) of the last commit touching any of files, or None."""
    cwd = os.path.dirname(files[0])
    out = git_out(cwd, "log", "-1", "--format=%ct%x1f%an%x1f%s", "--",
                  *[os.path.relpath(f, cwd) for f in files])
    if not out:
        return None
    fields = out.split(u"\x1f")
    if len(fields) != 3 or not fields[0].isdigit():
        return None
    return int(fields[0]), fields[1], fields[2]


_repo_cache = {}


def repo_root(path):
    """Git work tree root containing path (cached per folder), or None."""
    folder = os.path.dirname(path)
    if folder not in _repo_cache:
        top = git_out(folder, "rev-parse", "--show-toplevel")
        _repo_cache[folder] = os.path.normcase(os.path.normpath(top)) if top else None
    return _repo_cache[folder]


def repo_commit(root):
    """Current commit of a documents repository: dict for the page footer, or None."""
    out = git_out(root, "log", "-1", "--format=%h%x1f%cd%x1f%an%x1f%s", "--date=format:%Y-%m-%d %H:%M")
    if not out or out.count(u"\x1f") != 3:
        return None
    short, date, author, subject = out.split(u"\x1f")
    return {
        "name": os.path.basename(root),
        "branch": git_out(root, "rev-parse", "--abbrev-ref", "HEAD") or u"?",
        "short": short, "date": date, "author": author, "subject": subject,
    }


def document_change(src, html, date_source):
    """(timestamp, tooltip, from_git) of the last change: git history of the source and
    its inserted files, else HTML mtime (tooltip is then empty)."""
    if date_source == "git" and src:
        found = {}
        collect_sources(src, found)
        if found:
            commit = git_last_commit(sorted(found.values()))
            if commit:
                ts, author, subject = commit
                return ts, u"%s: %s" % (author, subject), True
    return int(os.path.getmtime(html)), u"", False


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
            ts, tooltip, from_git = document_change(src, html, date_source)
            docs.append({
                "title": title or resolve_title(src, html),
                "html": html,
                "ts": ts,
                "date": time.strftime("%Y-%m-%d", time.localtime(ts)),
                "tooltip": tooltip,
                # HTML file time after a rebuild is always "today": not a reason for NEW
                "dated_by_git": from_git or date_source != "git",
                "repo": repo_root(src or html),
            })
    if col.get("sort") == "title":
        docs.sort(key=lambda d: d["title"].lower())
    return docs


def render(cfg, columns, out_dir):
    esc = lambda s: cgi.escape(s, True)
    title = esc(cfg.get("title", "Documents repository"))
    use_filter = cfg.get("filter", True)
    show_dates = cfg.get("show_dates", True)
    mark_new = cfg.get("mark_new", True)
    max_cols = cfg.get("max_columns_per_row")
    show_formats = cfg.get("show_formats", True)
    recent_count = int(cfg.get("recent", 8))
    # "new" = changed today or within the previous new_days - 1 days
    new_days = max(1, int(cfg.get("new_days", 2)))
    new_since = time.strftime("%Y-%m-%d", time.localtime(time.time() - (new_days - 1) * 86400))
    generated = time.strftime("%Y-%m-%d %H:%M")

    def render_item(d, column_title=None):
        # HTML and PDF open in a new tab; docx is a download, so it keeps the default
        item = u'<li><a href="%s" target="_blank" rel="noopener">%s</a>' % (make_href(d["html"], out_dir), esc(d["title"]))
        if mark_new and d["dated_by_git"] and d["date"] >= new_since:
            item += u'<span class="new">new</span>'
        if show_dates:
            tip = u' title="%s"' % esc(d["tooltip"]) if d["tooltip"] else u""
            item += u'<time%s>%s</time>' % (tip, d["date"])
        if show_formats:
            # Secondary links: only formats that are built next to the HTML
            for ext in (".pdf", ".docx"):
                other = os.path.splitext(d["html"])[0] + ext
                if os.path.isfile(other):
                    target = u' target="_blank" rel="noopener"' if ext == ".pdf" else u""
                    item += u'<a class="fmt" href="%s"%s>%s</a>' % (make_href(other, out_dir), target, ext[1:])
        if column_title:
            item += u'<span class="col">%s</span>' % esc(column_title)
        return item + u'</li>'

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
        out.append(u'<span id="filter-count"></span>')
        out.append(u'<input id="filter" type="search" placeholder="Filter documents (press /)" title="Press / to focus, Esc to clear" aria-label="Filter documents">')
    out.append(u'</header>')

    if recent_count > 0:
        # Most recently changed documents across all columns (each document once)
        seen, recent = set(), []
        for col, docs in columns:
            for d in docs:
                key = os.path.normcase(d["html"])
                if key not in seen:
                    seen.add(key)
                    recent.append((d, col["title"]))
        recent.sort(key=lambda x: -x[0]["ts"])
        out.append(u'<section id="recent"><h2>Recently updated</h2><ul>')
        for d, col_title in recent[:recent_count]:
            out.append(render_item(d, col_title))
        out.append(u'</ul></section>')

    out.append(u'<main style="--max-cols:%d">' % int(max_cols) if max_cols else u'<main>')
    for col, docs in columns:
        out.append(u'<section><h2>%s</h2><ul>' % esc(col["title"]))
        for d in docs:
            out.append(render_item(d))
        out.append(u'</ul></section>')
    out.append(u'</main>')
    footer = [u'Generated %s' % generated]
    # The production index is rebuilt by a scheduled task every 30 minutes
    update_every = int(cfg.get("update_every_min", 30))
    if update_every > 0:
        footer.append(u'Updated every %d minutes' % update_every)
    footer.append(u'prodoc %s' % util.get_toolver())
    lines = [u' &middot; '.join(footer)]
    if cfg.get("show_repo_commit", True):
        # Commit of each documents repository the index links to, one line each
        roots = []
        for _, docs in columns:
            for d in docs:
                if d["repo"] and d["repo"] not in roots:
                    roots.append(d["repo"])
        for root in roots:
            c = repo_commit(root)
            if c:
                lines.append(u'Documents: <span class="repo" title="%s">%s @ %s %s (%s)</span>' % (
                    esc(u"%s: %s" % (c["author"], c["subject"])), esc(c["name"]), esc(c["branch"]),
                    esc(c["short"]), esc(c["date"])))
    out.append(u'<footer>%s</footer>' % u''.join(u'<div>%s</div>' % l for l in lines))
    if use_filter:
        out.append(u'<script>%s</script>' % read_text(JS_FILE).strip())
    out.append(u'</body>')
    out.append(u'</html>')
    return u"\n".join(out) + u"\n"


def write_atomic(path, text):
    """Write to a temporary file, then replace path in one step, so a web server
    never serves a half-written page."""
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    try:
        import ctypes
        # MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
        if ctypes.windll.kernel32.MoveFileExW(unicode(tmp), unicode(path), 0x1 | 0x8):
            return
    except (ImportError, AttributeError):
        pass
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)


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

    # Skip git lookups when dates are neither displayed nor used for the "new" badge
    needs_dates = cfg.get("show_dates", True) or cfg.get("mark_new", True)
    date_source = cfg.get("date_source", "git") if needs_dates else "file"
    columns = []
    for col in cfg["columns"]:
        docs = collect_documents(col, root, out_file, date_source)
        if docs:
            columns.append((col, docs))
        else:
            warn("column '%s' has no documents, skipped" % col["title"])

    if not columns:
        # Typical mistake: a JSON with web-root paths ("repo/src/...") run from another folder
        fail(u"no documents found. Paths in %s are relative to its folder (%s); "
             u"put the JSON in the folder its paths start from (e.g. the web root) and run it there. "
             u"Output not written." % (os.path.basename(json_file), root))
    write_atomic(out_file, render(cfg, columns, out_dir))
    print console(u"Generated %s (%d documents)" % (out_file, sum(len(d) for _, d in columns)))


if __name__ == "__main__":
    main()
