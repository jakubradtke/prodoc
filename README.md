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
* Without an explicit `title`, the title comes from the YAML front matter `title`, then the first `#` heading, then the file name.
* Documents whose `.html` is not built yet are skipped with a warning.
* Optional keys: `output` (default `index.html`), `filter` (search box, default `true`), `show_dates` (last change date per document, default `true`), `mark_new` ("new" badge for documents whose last change date is the day the index is generated, default `true`), `date_source` (`git`, the default: date of the last commit that touched the source or any file it inserts with `[file.md]`, falling back to the HTML modification date outside git or for untracked files; `file`: HTML modification date), `max_columns_per_row`, and per column `sort` (`title` or `none`, the default JSON order).

Build the documents first, then run:

    build_index.bat [path\to\index.json] [-o output.html]

Without arguments, `index.json` in the current directory is used. See `example/index.json`.