@echo off

set "cmd_dir=%~dp0"
if "%cmd_dir:~-1%"=="\" set "cmd_dir=%cmd_dir:~0,-1%"

set "python_cmd=%PRODOC_PYTHON%"

echo %PATH% | "C:\Windows\System32\find.exe" /i "%cmd_dir%" > nul
if %errorlevel% neq 0 (
    echo ERROR: The directory %cmd_dir% is not in the PATH.
    exit /b 1
)

if not defined python_cmd (
    echo ERROR: PRODOC_PYTHON is not set.
    exit /b 1
)
if not exist "%python_cmd%" (
    echo ERROR: PRODOC_PYTHON="%python_cmd%" does not point to an existing file.
    exit /b 1
)

:call_build
call %PRODOC_PYTHON% %PRODOC_DIR%\pm_tools\scripts\mmd2doc.py %*
exit /b

