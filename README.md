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