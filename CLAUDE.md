# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Prodoc is a Windows-only framework that turns extended Markdown (`.md` / `.mmd`) into single-file HTML, DOCX, or PDF. It is a fork of [pm_tools](https://github.com/glexey/pm_tools). Nearly all logic lives in `pm_tools/`; third-party binaries (Pandoc, Graphviz, PlantUML, ImageMagick, wkhtmltopdf, PhantomJS, batik) are vendored in-tree and located via `toolpath()` in `mmd2doc.py`.

## Runtime constraints

- **Python 2.7** (`.python-version` = 2.7.18). Code uses Python 2 syntax (`print x`, `except E, e`, `iteritems`). Do not introduce Python 3-only syntax in `pm_tools/`.
- Exception: `scripts/gen_index_page.py` is Python 3 (type hints, `pathlib`) and runs separately.
- Required env vars: `PRODOC_PYTHON` (dir containing Python 2 `python.exe`), `PRODOC_HOME` (repo root). Java must be installed (found by `util.locate_java()`; used by PlantUML, ditaa, batik).
- Visio/Excel plugins drive MS Office via COM (`pywin32`, `docsrv.py`), so they need Office installed.
- Python deps are listed in README.md (pinned versions matter, e.g. `openpyxl==2.4.0`, `html5lib==0.999`, `lxml==3.8.0`).

## Commands

```bat
build.bat doc.md            :: HTML (default)
build_docx.bat doc.md       :: DOCX, uses pm_tools/stylesheets/reference.dotx
build_pdf.bat doc.md        :: PDF via intermediate doc_pdf.html + wkhtmltopdf
build_all.bat               :: build every *.md/*.mmd under CWD recursively (also _docx_all / _pdf_all)
```

All wrappers call `%PRODOC_PYTHON%\python.exe %PRODOC_HOME%\pm_tools\scripts\mmd2doc.py [--fmt html|docx|pdf] ...`. Useful flags: `--nopre` (skip preprocessor), `--verbose`, `--perf` (per-plugin timing), `--append FILE` (append preprocessed file after a page break), `--dotx` (override reference doc), `--pandoc_args`, `--slides` (reveal.js).

There is no test suite. Verify changes by building `pm_tools/doc/example.mmd`. It is the feature showcase and exercises every plugin. Files whose name starts with `_` are chapters. `build_all` skips them; they are only pulled in via includes.

## Architecture

Pipeline in `pm_tools/scripts/mmd2doc.py`:

1. `build_doc()` resolves inputs and output names, then constructs `PandocPreproc`.
2. `PandocPreproc.parse()` tokenizes source with an ordered regex list: `COMMENT` > plugin fences (```` ```<token>(args) ... ``` ````) > `VERBATIM` > `IMAGE` > `INSERT_FILE` > `HEADER` > `CODE`. The main loop pops tokens and dispatches them. Plugin fence args are parsed as Python call args and passed to `plugin.process(code, *args, **kwargs)`.
3. Include syntax `[path/file.md]` on its own line inlines another file. `[!file.md]` resets the heading level. `[docx:file.md]` / `[html:...]` / `[pdf:...]` include only for that output format. Included files push `PUSH_DIR`/`POP_DIR` tokens, so relative paths resolve against the included file's dir (`self.dirs[-1]`). Heading levels shift via `g.hlevel`.
4. Preprocessed markdown goes to a temp file. Then Visio conversion runs, SVG fixups run, and for DOCX/email SVG is converted to PNG.
5. Pandoc renders. For HTML, the output is post-processed with BeautifulSoup. SVGs are injected after pandoc through hash placeholders (`g.svg_hash`), because pandoc is slow and lossy on large inline SVG.
6. PDF: pandoc produces `_pdf.html`, then `wkhtmltopdf` converts it.

Generated artifacts (rendered diagrams, etc.) go into an `auto/` dir next to each source file. `exists_and_newer()` skips regeneration when the output is up to date. The build aborts on any `c:\` path that leaks into the output (crude local-path guard in `parse()`).

### Plugins (`pm_tools/plugins/<name>/`)

`plugins/__init__.py` auto-discovers every subpackage with `__init__.py`. Each module exposes `new = PluginClass` (or a list). The class constructor gets the preprocessor, sets `self.token`, and calls `pp.register_plugin(self)`. The token must be unique. Optional hooks: `preprocess(s)`, `process_mismatch(s)` (plain text), `postprocess_html(s)`, `postprocess_soup(soup)`. Also supported: `require_plugins` for cross-plugin refs and a `send` dict for inter-plugin messages.

The preprocessor instance is the plugin API. Plugins call `pp.get_source(...)` (write inline code to a file or resolve a filename, and decide whether an update is needed), `pp.img2md(...)`, `pp._call(...)`, `pp.toolpath(...)`, `pp.dot_exe`, `pp.java_exe`, `pp.error(...)`. `pm_tools/plugins/dot/dot.py` is the minimal reference plugin.

### Other pieces

- `pm_tools/frontend/` holds the JS/HTML injected into HTML output (sidebar and more). `pm_tools/stylesheets/` holds CSS, the PDF footer, and `reference.dotx` for DOCX styling.
- `pm_tools/tools.cfg` sets the MathJax/font CDN URLs. `pm_tools/version.txt` holds the tool version stamped into docs (bump it to trigger rebuilds).
- `scripts/gen_index_page.py` (Python 3) builds an `index.html` for a docs repo from the directory tree and YAML front matter (`title`, `classification`).

## Repo conventions

- `.agent/skills/` is the canonical skills directory. `.cursor/skills` and `.claude/skills` are junctions to it. Rules in `.cursor/rules/` only route to a skill; the procedure lives in the skill's `SKILL.md`.
