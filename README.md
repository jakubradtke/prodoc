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
* Optional keys: `output` (default `index.html`), `filter` (search box, default `true`), `show_dates` (last change date per document, default `true`), `mark_new` ("new" badge for recently changed documents, default `true`), `new_days` (a document is "new" when changed today or in the previous `new_days - 1` days, default `2`), `recent` (size of the "Recently updated" list at the top of the page, `0` turns it off, default `8`), `show_repo_commit` (footer shows the branch, commit and commit time of each documents repository, with author and message on hover, default `true`), `update_every_min` (footer note "Updated every N minutes", default `30` to match the scheduled rebuild, `0` turns it off), `show_formats` (small `pdf`/`docx` links next to the HTML link when those files exist next to the HTML, default `true`), `date_source` (`git`, the default: date of the last commit that touched the source or any file it inserts with `[file.md]`, falling back to the HTML modification date outside git or for untracked files; `file`: HTML modification date), `max_columns_per_row`, and per column `sort` (`title` or `none`, the default JSON order).

Build the documents first, then run:

    build_index.bat [path\to\index.json] [-o output.html]

Without arguments, `index.json` in the current directory is used. See `example/index.json`.