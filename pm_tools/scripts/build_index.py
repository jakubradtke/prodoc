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
  "search": true,                        # optional, content search; writes <output>-search.js next to the page
  "show_repo_commit": true,              # optional, footer shows branch/commit of the documents repo
  "date_source": "git",                  # optional: "git" (last commit of source + inserted
                                         #   files, falls back to "file") or "file" (HTML mtime)
  "max_columns_per_row": 3,              # optional, grid auto-fits when omitted
  "home_title": "General",               # optional, tab label of the main page (default: title)
  "columns": [
    {
      "title": "Architecture",
      "sort": "title",                   # optional: "title" or "none" (JSON order)
      "documents": [
        "path/to/doc.md",                # link goes to path/to/doc.html
        {"path": "path/to/other.mmd", "title": "Explicit title"},
        {"path": "path/to/var.md", "variant": "26.H2"},   # link goes to path/to/var.26.H2.html
        "path/**/*.md"                   # globs: *, ?, ** (recursive)
      ]
    }
  ],
  "releases": [                          # optional, one tab (sub-page) per release
    {"id": "26.H2", "title": "26.H2", "dir": "26H2"},
    {"id": "legacy", "title": "Legacy", "dir": "Legacy", "archived": true}
  ],
  "release_columns": [                   # columns of every release tab; {{key}} = value from the release
    {"title": "Validation", "documents": ["Validation/{{dir}}/*.md"]}
  ],
  "pages": [                             # optional, free-form extra tabs
    {"title": "Tools", "output": "index-tools.html", "columns": [...]}
  ]
}

Documents with "variants:" in their YAML header are built to <doc>.<variant>.html. On a release
tab (variant = release id) such a document links its variant build, or is left out when the
release is not in its variants list. On other tabs it is listed once per variant.
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

import copy

import yaml

import util
import symbols

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
    if not isinstance(cfg, dict):
        fail("%s: top level must be a JSON object" % fname)
    for key in ("pages", "releases", "release_columns"):
        if not isinstance(cfg.get(key, []), list):
            fail("%s: '%s' must be a list" % (fname, key))
    pages, releases = cfg.get("pages", []), cfg.get("releases", [])
    if not isinstance(cfg.get("columns", []), list) or (not cfg.get("columns") and not pages and not releases):
        fail("%s: 'columns' must be a non-empty list (or define 'releases' or 'pages')" % fname)
    if cfg.get("date_source", "git") not in ("git", "file"):
        fail("%s: invalid 'date_source' (use 'git' or 'file')" % fname)
    validate_columns(fname, cfg.get("columns", []))
    if releases and not cfg.get("release_columns") and not all(r.get("columns") for r in releases if isinstance(r, dict)):
        fail("%s: 'releases' needs 'release_columns' (or 'columns' in every release)" % fname)
    validate_columns(fname, cfg.get("release_columns", []))
    ids = set()
    for i, rel in enumerate(releases):
        if not isinstance(rel, dict) or not rel.get("id"):
            fail("%s: release #%d has no 'id'" % (fname, i + 1))
        rid = unicode(rel["id"])
        if not re.match(r"^[\w.\-]+$", rid):
            fail("%s: release id '%s' may contain only letters, digits, '.', '-' and '_'" % (fname, rid))
        if rid in ids:
            fail("%s: release '%s' is listed twice" % (fname, rid))
        ids.add(rid)
        if not isinstance(rel.get("columns", []), list):
            fail("%s: release '%s': 'columns' must be a list" % (fname, rid))
        validate_columns(fname, rel.get("columns", []))
    for i, page in enumerate(pages):
        if not isinstance(page, dict) or not page.get("title"):
            fail("%s: page #%d has no 'title'" % (fname, i + 1))
        if not page.get("output"):
            fail("%s: page '%s' has no 'output' file name" % (fname, page["title"]))
        if not isinstance(page.get("columns"), list) or not page["columns"]:
            fail("%s: page '%s' has no 'columns' list" % (fname, page["title"]))
        validate_columns(fname, page["columns"])
    return cfg


def validate_columns(fname, columns):
    for i, col in enumerate(columns):
        if not isinstance(col, dict) or not col.get("title"):
            fail("%s: column #%d has no 'title'" % (fname, i + 1))
        if not isinstance(col.get("documents"), list):
            fail("%s: column '%s' has no 'documents' list" % (fname, col["title"]))
        if col.get("sort", "none") not in ("none", "title"):
            fail("%s: column '%s' has invalid 'sort' (use 'title' or 'none')" % (fname, col["title"]))


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


def html_title(html):
    """<title> of a built HTML page: the document title after symbol substitution
    ({{NAME}} in the YAML title), or None."""
    with io.open(html, "r", encoding="utf-8", errors="replace") as f:
        head = f.read(200000)
    m = re.search(r"<title>(.*?)</title>", head, re.S | re.I)
    if not m:
        return None
    return html_text(m.group(1)) or None


def resolve_title(src, html):
    """Title from YAML front matter, then first '# ' heading, then file name. A YAML title
    with symbols ({{NAME}}) or conditions (<!--if:-->) is taken from the built HTML <title>
    instead, where it is already substituted."""
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
                if u"{{" in title or u"<!--" in title:
                    title = html_title(html) or title
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


def source_variants(src):
    """Variant names from "variants:" in the YAML header of a source (unicode), or []."""
    if not src or not os.path.isfile(src):
        return []
    try:
        return [v.decode("utf-8") for v in symbols.header_variants(symbols.read_header(read_text(src)))]
    except symbols.SymbolError as e:
        warn(u"%s: %s" % (src, e))
        return []


def variant_html(html, variant):
    # Variant builds are named <doc>.<variant>.html (see "variants" in mmd2doc.py)
    return u"%s.%s.html" % (os.path.splitext(html)[0], variant)


def collect_documents(col, root, out_file, date_source, page_variant=None):
    """Documents of one column. page_variant: release id of a release tab; documents with
    "variants:" then link that variant or are left out. Template columns (release tabs) skip
    missing documents silently, because older releases do not have every document."""
    docs = []
    optional = col.get("_template", False)
    for entry in col["documents"]:
        if isinstance(entry, dict):
            path, title, variant = entry.get("path"), entry.get("title"), entry.get("variant")
        else:
            path, title, variant = entry, None, None
        if not path:
            fail("column '%s': document entry without 'path'" % col["title"])
        path = path.replace("\\", "/")
        if "*" in path or "?" in path:
            files = expand_glob(root, path)
            if not files and not optional:
                warn("column '%s': pattern '%s' matched no files" % (col["title"], path))
        else:
            files = [os.path.join(root, *path.split("/"))]
        for fname in files:
            src, html = find_source(os.path.normpath(fname))
            if variant:
                htmls = [variant_html(html, variant)]
            else:
                variants = source_variants(src)
                if not variants:
                    htmls = [html]
                elif page_variant:
                    htmls = [variant_html(html, page_variant)] if page_variant in variants else []
                else:
                    htmls = [variant_html(html, v) for v in variants]
            for html in htmls:
                if os.path.normcase(html) == os.path.normcase(out_file):
                    continue
                if not os.path.isfile(html):
                    if not (optional and src is None):
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


PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z_][\w\-]*)\}\}")


def fill_placeholders(value, values, where):
    """Copy of a JSON value with {{key}} in strings replaced from values (unknown key: error)."""
    if isinstance(value, basestring):
        def repl(m):
            if m.group(1) not in values:
                fail(u"%s: unknown placeholder {{%s}} (keys of this release: %s)"
                     % (where, m.group(1), u", ".join(sorted(values))))
            return values[m.group(1)]
        return PLACEHOLDER_RE.sub(repl, value)
    if isinstance(value, list):
        return [fill_placeholders(v, values, where) for v in value]
    if isinstance(value, dict):
        return dict((k, fill_placeholders(v, values, where)) for k, v in value.items())
    return value


def build_pages(cfg, out_file):
    """All tabs of the index, in navigation order: main page, releases, extra "pages",
    archived releases last. Each page: dict(title, out, columns, variant, archived, home)."""
    out_dir = os.path.dirname(out_file)
    home = dict(title=cfg.get("home_title") or cfg.get("title", "Documents repository"), out=out_file,
                columns=cfg.get("columns", []), variant=None, archived=False, home=True)
    active, archived = [], []
    for rel in cfg.get("releases", []):
        rid = unicode(rel["id"])
        values = dict((k, unicode(v)) for k, v in rel.items()
                      if isinstance(v, (basestring, int, float)) and not isinstance(v, bool))
        where = u"release '%s'" % rid
        columns = []
        for col in fill_placeholders(copy.deepcopy(cfg.get("release_columns", [])), values, where):
            col["_template"] = True
            columns.append(col)
        columns += fill_placeholders(copy.deepcopy(rel.get("columns", [])), values, where)
        page = dict(title=unicode(rel.get("title") or rid),
                    out=os.path.normpath(os.path.join(out_dir, rel.get("output") or u"index-%s.html" % rid)),
                    columns=columns, variant=rid,
                    archived=bool(rel.get("archived")), home=False)
        (archived if page["archived"] else active).append(page)
    extra = [dict(title=p["title"], out=os.path.normpath(os.path.join(out_dir, p["output"])),
                  columns=p["columns"], variant=None, archived=False, home=False)
             for p in cfg.get("pages", [])]
    pages = [home] + active + extra + archived
    seen = set()
    for page in pages:
        key = os.path.normcase(page["out"])
        if key in seen:
            fail(u"two tabs write the same file: %s" % page["out"])
        seen.add(key)
        # Links between tabs and the shared search file assume one folder
        if os.path.normcase(os.path.dirname(page["out"])) != os.path.normcase(out_dir):
            fail(u"tab '%s': output %s must be in the folder of the main page (%s)"
                 % (page["title"], page["out"], out_dir))
    return pages


def render(cfg, columns, out_dir, search_src=None, tab_title=None, nav=None, recent=None, empty_text=None):
    """HTML of one index page.
    nav: tabs when the index has several pages, [dict(title, href (None = this page), archived)].
    recent: [(document, label)] for "Recently updated"; None = the newest documents of this page.
    empty_text: shown instead of the columns when the page has no documents."""
    esc = lambda s: cgi.escape(s, True)
    title = esc(cfg.get("title", "Documents repository"))
    page_title = title + (u" &middot; " + esc(tab_title) if tab_title else u"")
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
        u'<title>%s</title>' % page_title,
        u'<style>%s</style>' % read_text(CSS_FILE).strip(),
        u'</head>',
        u'<body>',
        u'<header><h1>%s</h1>' % title,
    ]
    if use_filter:
        out.append(u'<span id="filter-count"></span>')
        out.append(u'<input id="filter" type="search" placeholder="Filter titles (press /)" title="Press / to focus, Esc to clear" aria-label="Filter document titles">')
        if search_src:
            # Version in the URL so browsers do not keep an old search index from cache
            out.append(u'<input id="content-search" type="search" placeholder="Search content (press \\)" '
                       u'title="Press \\ to focus, Esc to clear" aria-label="Search document content" data-search="%s?v=%s">'
                       % (esc(urllib.quote(search_src.encode("utf-8"))), time.strftime("%Y%m%d%H%M%S")))
            out.append(u'<label class="match-case" title="Case-sensitive content search">'
                       u'<input id="match-case" type="checkbox"> Match case</label>')
    out.append(u'</header>')
    if nav:
        # Tabs: main page, releases, extra pages, archived releases. This page is not a link.
        links = []
        for tab in nav:
            cls = [u"tab"]
            if tab["href"] is None:
                cls.append(u"active")
            if tab["archived"]:
                cls.append(u"archived")
            label = esc(tab["title"])
            if tab["href"] is None:
                links.append(u'<span class="%s" aria-current="page">%s</span>' % (u" ".join(cls), label))
            else:
                links.append(u'<a class="%s" href="%s">%s</a>' % (u" ".join(cls), esc(tab["href"]), label))
        out.append(u'<nav class="pages">%s</nav>' % u''.join(links))
    if search_src:
        out.append(u'<div id="content-results" hidden><h2></h2><ul></ul></div>')

    if recent is None and recent_count > 0:
        # Most recently changed documents across all columns (each document once)
        seen, recent = set(), []
        for col, docs in columns:
            for d in docs:
                key = os.path.normcase(d["html"])
                if key not in seen:
                    seen.add(key)
                    recent.append((d, col["title"]))
        recent.sort(key=lambda x: -x[0]["ts"])
    if recent:
        out.append(u'<section id="recent"><h2>Recently updated</h2><ul>')
        for d, label in recent[:recent_count]:
            out.append(render_item(d, label))
        out.append(u'</ul></section>')

    if not columns and empty_text:
        out.append(u'<p class="empty">%s</p>' % esc(empty_text))
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


SECTION_RE = re.compile(r'<section\b[^>]*\bid="([^"]+)"[^>]*>', re.I)
HEADING_RE = re.compile(r'<h[1-6]\b[^>]*>(.*?)</h[1-6]>', re.I | re.S)
NOISE_RE = re.compile(r'<(script|style|svg|head)\b.*?</\1>|<img\b[^>]*>', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')
_unescape = __import__("HTMLParser").HTMLParser().unescape


def html_text(fragment):
    return u" ".join(_unescape(TAG_RE.sub(u" ", fragment)).split())


def extract_sections(html):
    """[(section id, heading, own text)] of a pandoc HTML document (--section-divs).
    Text of a section stops at the next <section>, so subsections are separate entries;
    page chrome outside sections (sidebar, forms) is ignored."""
    s = NOISE_RE.sub(u" ", read_text(html))
    marks = list(SECTION_RE.finditer(s))
    out = []
    for i, m in enumerate(marks):
        # Only pandoc chapters (class="levelN"); other sections (feedback form, sidebar)
        # still end the previous chapter but are not indexed
        if not re.search(r'class="[^"]*\blevel\d', m.group(0)):
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(s)
        chunk = s[m.end():end]
        h = HEADING_RE.search(chunk)
        heading = html_text(h.group(1)) if h else u""
        text = html_text(chunk[h.end():] if h else chunk)
        if heading or text:
            out.append((m.group(1), heading, text))
    return out


def write_search_index(path, columns, out_dir, labels=None):
    """Write <output>-search.js: section texts of all documents for the content search in index.js.
    labels: {normcase(html): tab title} when the index has several tabs; results then show the tab."""
    docs, entries, seen = [], [], {}
    for _, col_docs in columns:
        for d in col_docs:
            key = os.path.normcase(d["html"])
            if key in seen:
                continue
            seen[key] = len(docs)
            href = make_href(d["html"], out_dir)
            docs.append([d["title"], href] + ([labels.get(key, u"")] if labels is not None else []))
            for sid, heading, text in extract_sections(d["html"]):
                entries.append([seen[key], sid, heading, text])
    data = json.dumps({"docs": docs, "s": entries}, ensure_ascii=False, separators=(",", ":"))
    if isinstance(data, str):
        data = data.decode("utf-8")
    write_atomic(path, u"window.PRODOC_SEARCH=%s;\n" % data)
    return len(docs), len(entries)


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

    # Tabs: main page, one per release, extra "pages". All outputs sit next to the main page;
    # -o moves the whole set.
    pages = build_pages(cfg, out_file)
    multi = len(pages) > 1
    for page in pages:
        page["data"] = []
        for col in page["columns"]:
            docs = collect_documents(col, root, page["out"], date_source, page["variant"])
            if docs:
                page["data"].append((col, docs))
            elif not col.get("_template"):
                warn(u"page '%s': column '%s' has no documents, skipped" % (page["title"], col["title"]))
    all_columns = [c for page in pages for c in page["data"]]
    total = len(set(os.path.normcase(d["html"]) for _, docs in all_columns for d in docs))
    if total == 0:
        # Typical mistake: a JSON with web-root paths ("repo/src/...") run from another folder
        fail(u"no documents found. Paths in %s are relative to its folder (%s); "
             u"put the JSON in the folder its paths start from (e.g. the web root) and run it there. "
             u"Output not written." % (os.path.basename(json_file), root))

    # Tab of each document, for labels in the content search and in "Recently updated" on the
    # main page. A release tab wins over the main page.
    labels = {}
    for page in pages[1:] + pages[:1]:
        for _, docs in page["data"]:
            for d in docs:
                labels.setdefault(os.path.normcase(d["html"]), page["title"])

    search_src = None
    if cfg.get("search", True) and cfg.get("filter", True):
        # One content search file for all tabs, next to the main page; loaded by index.js only when used
        search_file = os.path.splitext(out_file)[0] + "-search.js"
        n_docs, n_sections = write_search_index(search_file, all_columns, out_dir, labels if multi else None)
        search_src = os.path.basename(search_file)
        print console(u"Search index %s (%d documents, %d sections)" % (search_file, n_docs, n_sections))

    recent_count = int(cfg.get("recent", 8))
    for page in pages:
        nav, recent, tab_title = None, None, None
        if multi:
            nav = [dict(title=p["title"], href=None if p is page else make_href(p["out"], out_dir),
                        archived=p["archived"]) for p in pages]
            tab_title = None if page["home"] else page["title"]
            if page["home"] and recent_count > 0:
                # Main page: newest documents of all tabs, labelled with the tab (column on the main page)
                seen, recent = set(), []
                for p in pages:
                    for col, docs in p["data"]:
                        for d in docs:
                            key = os.path.normcase(d["html"])
                            if key not in seen:
                                seen.add(key)
                                recent.append((d, col["title"] if p["home"] else labels[key]))
                recent.sort(key=lambda x: -x[0]["ts"])
            elif sum(len(docs) for _, docs in page["data"]) <= recent_count:
                recent = []  # small tab: the list would repeat the whole page
        empty = u"No documents for this release yet." if page["variant"] else u"No documents."
        write_atomic(page["out"], render(cfg, page["data"], out_dir, search_src, tab_title, nav, recent, empty))
        print console(u"Generated %s (%d documents)" % (page["out"], sum(len(d) for _, d in page["data"])))


if __name__ == "__main__":
    main()
