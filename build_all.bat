@echo off
setlocal enabledelayedexpansion

set "ROOT=%CD%"

echo.
echo ==============================
echo   PRODOC Build ALL Started
echo ==============================
echo.

REM Counter for processed files
set "COUNT=0"

for %%E in (mmd md) do (
    for /r "%ROOT%" %%F in (*.%%E) do (
        set "name=%%~nF"
        REM skip if first char is "_"
        if /i not "!name:~0,1!"=="_" (
            echo [%%~nF] Processing: %%F
            call build.bat "%%F"
            set /a COUNT+=1
        )
    )
)

if %COUNT% EQU 0 (
    echo No .mmd or .md files found to process.
) else (
    echo.
    echo Processed %COUNT% file(s)
)
echo.
echo ==============================
echo   PRODOC Batch Build Finished
echo ==============================

endlocal
