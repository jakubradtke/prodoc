@echo off
rem Build documents: build.bat [mmd2doc options] file.md [file2.md ...]
rem build_docx.bat / build_pdf.bat call this script with --fmt.
setlocal
if not defined PRODOC_HOME goto :noenv
if not defined PRODOC_PYTHON goto :noenv
if not exist "%PRODOC_PYTHON%\python.exe" goto :nopython

"%PRODOC_PYTHON%\python.exe" "%PRODOC_HOME%\pm_tools\scripts\mmd2doc.py" %*
exit /b %ERRORLEVEL%

:noenv
echo ERROR: PRODOC_HOME and PRODOC_PYTHON must be set (see README).
exit /b 9

:nopython
echo ERROR: python.exe not found in PRODOC_PYTHON=%PRODOC_PYTHON%
exit /b 9
