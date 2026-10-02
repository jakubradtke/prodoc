@echo off
rem Generate index.html from a JSON description: build_index.bat [index.json] [-o output.html]
setlocal
if not defined PRODOC_HOME goto :noenv
if not defined PRODOC_PYTHON goto :noenv
if not exist "%PRODOC_PYTHON%\python.exe" goto :nopython

"%PRODOC_PYTHON%\python.exe" "%PRODOC_HOME%\pm_tools\scripts\build_index.py" %*
exit /b %ERRORLEVEL%

:noenv
echo ERROR: PRODOC_HOME and PRODOC_PYTHON must be set (see README).
exit /b 9

:nopython
echo ERROR: python.exe not found in PRODOC_PYTHON=%PRODOC_PYTHON%
exit /b 9
