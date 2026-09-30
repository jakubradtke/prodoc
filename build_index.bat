@echo off

call %PRODOC_PYTHON%\python.exe %PRODOC_HOME%\pm_tools\scripts\build_index.py %*
exit /b
