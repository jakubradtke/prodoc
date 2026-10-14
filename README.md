# PRODOC
Prodoc is a framework for creating technical documentation in Markdown.
It is built based on the open-source project [pm_tools](https://github.com/glexey/pm_tools).

## Installation
The simplest method to install the framework is by using the provided Windows installer, which includes all necessary dependencies. Please refer to the release section to download it.

## Steps to use prodoc without using Installer

### Required Environment Variables
* PRODOC_PYTHON
    * Provide the path to the directory containing the Python 2 executable
* PRODOC_HOME
    * Path to the PRODOC root folder
* PATH
    * Add PRODOC_HOME
* PRODOC_JAVA (optional)
    * Path to the JDK/JRE home directory. It overrides the Java found in the registry or PATH. PlantUML needs Java 11 or newer.

### Required dependencies
* Java
* Python 2 with following modules
    * pyinstaller==3.6
    * openpyxl==2.4.0
    * bs4
    * xlsxwriter
    * pyyaml
    * coverage
    * html5lib==0.999
    * tabulate
    * excel2img==1.1
    * lxml==3.8.0
    * SchemDraw
    * psutil
    * pythonnet
    * pywin32
    * markdown
    * markdown-include
* Microsoft Visio
    * needed when markdown includes vsdx file(s)

## Quick start

Create a file named `hello.md` with the following content:

    # Quick start example

    ## Hello, World

    ```plantuml("Communication to the world")
    Pm_doc -> World: Hello there
    ```

Run from the cmd console:

    build.bat hello.md

Above command should produce hello.html file

## Building many documents

    build_all.bat [html|docx|pdf] [folder]
    build_docx_all.bat [folder]
    build_pdf_all.bat [folder]

* Builds every `*.md` and `*.mmd` under the folder (default: current folder), except chapters whose name starts with `_` and files in `auto\` folders.
* Prints the failed documents at the end and returns exit code `1` when any document failed (`0` = all built, `2` = folder not found), so scheduled scripts can detect problems.
* `build_pdf.bat` reports `PDF not created` and fails when wkhtmltopdf did not produce a PDF, instead of failing silently.

## Index page

`build_index.bat` generates a single-file `index.html` that links to built HTML documents. The page layout comes from an `index.json` file kept next to the documents:

    {
      "title": "Documents repository",
      "max_columns_per_row": 3,
      "columns": [
        {
          "title": "Architecture",
          "sort": "title",
          "documents": [
            "Architecture/SAS/SAS.mmd",
            {"path": "Architecture/HLA/HLA.mmd", "title": "High Level Architecture"},
            "Validation/**/*.mmd"
          ]
        }
      ]
    }

* Paths are relative to the JSON file. They point to the source (`.md`/`.mmd`); the link goes to the `.html` file with the same name. Paths to `.html` files work too.
* Globs `*`, `?` and `**` are supported. Files starting with `_` and `auto/` directories are skipped.
* The `.md` and `.mmd` source extensions are interchangeable: `*.md` also matches `.mmd` files, and a path to a missing `doc.mmd` falls back to `doc.md` (and the other way round).
* Dates and the "new" badge come from git. git is taken from `PRODOC_GIT`, then `PATH`, then common install folders. When git is missing or fails (for example "dubious ownership" when a scheduled task runs as another user), a warning is printed, dates fall back to the HTML file time and no document is marked "new".
* Without an explicit `title`, the title comes from the YAML front matter `title`, then the first `#` heading, then the file name.
* Documents whose `.html` is not built yet are skipped with a warning.
* Content search: the filter box also searches the text of the documents (from 3 characters). Results link to the matching chapter (`doc.html#section`) with a highlighted snippet. The text is written to `<output>-search.js` next to the page (for example `iisstart-search.js`) and loaded only when the search is used. Publish it together with the page. Turn off with `"search": false`.
* `{"path": "doc.md", "variant": "internal"}` links the variant build `doc.internal.html` of a document with `variants:` (see "Symbols, conditional text and variants"). Without `variant`, a document with `variants:` is listed once per variant, except on release tabs (below).
* Release tabs: `releases` and `release_columns` split the index into tabs, one HTML file per tab, linked by a tab bar on every page. The main page (`index.html`, tab label `home_title`, default `title`) keeps the top-level `columns` for documents that belong to no release. Each release gets `index-<id>.html` with the columns of `release_columns`:

        {
          "title": "VROC Documentation",
          "home_title": "General",
          "columns": [ ...generic documents... ],
          "releases": [
            {"id": "27.H1",    "title": "27.H1",      "dir": "27.H1",    "vdir": "27H1"},
            {"id": "27.H1.nv", "title": "27.H1 NV",   "dir": "27.H1.nv", "vdir": "27H1_NV"},
            {"id": "26.H2",    "title": "26.H2",      "dir": "26.H2",    "vdir": "26H2"},
            {"id": "26.H2.nv", "title": "26.H2 NV",   "dir": "26.H2.nv", "vdir": "26H2_NV"},
            {"id": "legacy",   "title": "Legacy 9.x", "dir": "Legacy",   "vdir": "Legacy", "archived": true}
          ],
          "release_columns": [
            {"title": "Implementation", "documents": ["Implementation/{{dir}}/**/*.md"]},
            {"title": "Release package", "documents": ["Implementation/UefiPackage/UefiPackage.md"]},
            {"title": "Validation", "sort": "title", "documents": ["Validation/*/{{vdir}}/*.md"]}
          ]
        }

    * A release: `id` (required; also the variant name of documents with `variants:`), `title` (tab label, default `id`), `output` (default `index-<id>.html`), `archived` (muted tab, placed last), `columns` (extra columns for this release only) and any other keys, used as `{{key}}` placeholders in `release_columns`. Tabs keep the JSON order, so list the newest release first.
    * A document with `variants:` in its YAML header appears on a release tab as `<doc>.<id>.html` when the release `id` is in its variants list, and not at all otherwise. One source like `UefiPackage.md` with `variants: [26.H2, 26.H2.nv, legacy]` so fills three tabs.
    * A release column entry that matches no file is skipped without a warning, because older releases do not have every document. A tab without documents shows "No documents for this release yet."
    * Content search covers all tabs from every page and labels each result with its tab. "Recently updated" on the main page also covers all tabs. On a release tab it lists that tab only, and is left out when the tab has no more documents than the list size. `"recent": 0` turns the list off on all tabs.
    * All tab files are written next to the main page (`-o` moves them together).
    * For a new release, add one line to `releases` (and the matching variant in `build.cfg`, see "Symbols, conditional text and variants"). A No-VMD edition such as `27.H1.nv` is a release entry of its own with its own tab.
* `pages`: optional extra tabs with hand-written columns, `{"title": "Tools", "output": "index-tools.html", "columns": [...]}`. They come after the release tabs and before archived releases.
* Optional keys: `output` (default `index.html`), `filter` (search box, default `true`), `show_dates` (last change date per document, default `true`), `mark_new` ("new" badge for recently changed documents, default `true`), `new_days` (a document is "new" when changed today or in the previous `new_days - 1` days, default `2`), `recent` (size of the "Recently updated" list at the top of the page, `0` turns it off, default `8`), `show_repo_commit` (footer shows the branch, commit and commit time of each documents repository, with author and message on hover, default `true`), `update_every_min` (footer note "Updated every N minutes", default `30` to match the scheduled rebuild, `0` turns it off), `show_formats` (small `pdf`/`docx` links next to the HTML link when those files exist next to the HTML, default `true`), `date_source` (`git`, the default: date of the last commit that touched the source or any file it inserts with `[file.md]`, falling back to the HTML modification date outside git or for untracked files; `file`: HTML modification date), `max_columns_per_row`, and per column `sort` (`title` or `none`, the default JSON order).

Build the documents first, then run:

    build_index.bat [path\to\index.json] [-o output.html]

Without arguments, `index.json` in the current directory is used. See `example/index.json`.

## Symbols, conditional text and variants

One Markdown source can produce several documents: a customer and an internal edition, one edition per release, or a template filled for each release. Everything below runs on the raw text before plugins, so a diagram inside a dropped block is never rendered.

* **Symbols**: `{{NAME}}` is replaced by the value of symbol `NAME`. Only defined names are replaced; `{{UNKNOWN}}` and single-brace `{placeholders}` stay untouched. `\{{NAME}}` keeps `{{NAME}}` literally. Substitution covers the whole file, including the YAML header (`title: Package {{RELEASE}}`) and plugin blocks.
* **Conditional blocks**: `<!--if:EXPR-->` ... `<!--elif:EXPR-->` ... `<!--else-->` ... `<!--endif-->`. `EXPR` is a Python expression over the symbols (`==`, `!=`, `in`, `and`, `or`, `not`, parentheses, `defined("NAME")`; no builtins, no imports). Blocks nest. An undefined name makes the condition false (no error), so `<!--if:NAME-->` reads "when NAME is defined". A syntax error, an unclosed block or an orphan `<!--endif-->` stops the build with the file and line. Markers may sit inside a line, also in the YAML header. Markers inside inline code or a fenced code block are plain text, so documentation can show the syntax; inside plugin blocks such as ```` ```plantuml ```` they stay active. Without the preprocessor (`--nopre`) the markers are plain HTML comments and all text stays.
* **Variants**: `variants: [internal, customer]` in the YAML header builds the document once per variant, to `doc.internal.html` and `doc.customer.html` (`.docx` and `.pdf` likewise; the PDF intermediate is `doc.internal_pdf.html`). Generated files go to `auto\<variant>\`. Without `variants:` the output names do not change. `build.bat --variant internal doc.md` builds one variant, also for a document without `variants:`.

Symbols come from, highest priority first:

1. the command line: `build.bat --define NAME=VALUE --variant NAME doc.md` (`--define` is repeatable),
2. `build.cfg` in the document folder or any folder above it (Python syntax; other keys of a ProMark `build.cfg` are ignored):

        releases = ["9.4", "26.H2", "27.H1"]           # in order, so RELEASE >= "26.H2" works
        symbols  = {"PRODUCT": "VROC", "AUDIENCE": "customer", "NOVMD": False}
        variants = {
            "internal": {"AUDIENCE": "internal"},
            "legacy":   {"RELEASE": "9.4"},
            "26.H2":    {"RELEASE": "26.H2"},
            "26.H2.nv": {"RELEASE": "26.H2", "NOVMD": True},   # No-VMD edition of 26.H2
            "27.H1":    {"RELEASE": "27.H1"},
        }

    An edition such as No-VMD (`.nv`) is not a later release, so it stays out of `releases` and sets its own symbol instead: `<!--if:NOVMD-->` for No-VMD text, `<!--if:RELEASE >= "27.H1"-->` for features new in 27.H1 in both editions. Use the same variant ids as the release `id` in `index.json`.

3. include parameters `[_chapter.md||RELEASE:"26.H2",OS:Linux]` (values are strings, visible only inside the included file, which otherwise inherits the symbols of the including file; quote values containing commas),
4. `symbols:` in the YAML header (defaults, never override the sources above).

Built-in symbols: `VARIANT` (variant name, empty without one), `FMT` (`html`, `docx`, `pdf`). With `releases` in `build.cfg`, `RELEASE` becomes comparable by position in that list (`RELEASE >= "26.H1"`); a release name outside the list is an error. Without `releases`, `RELEASE` is a plain string.

Example, one source for two releases:

    ---
    title: UEFI Package {{RELEASE}}
    variants: [26.H2, legacy]
    ---
    <!--if:RELEASE >= "26.H2"-->
    | `VrocCryptoDxe.efi` | Crypto provider |
    <!--endif-->
    `HwKeySedDxe.efi` is not part of the VROC {{RELEASE}} kit.

See `pm_tools/doc/example.mmd` (chapter "Symbols, conditional text and variants"), `pm_tools/doc/variants.mmd` and `pm_tools/doc/build.cfg`.
