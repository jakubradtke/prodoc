@echo off
setlocal enabledelayedexpansion

set "ROOT=%CD%"

for /r "%ROOT%" %%F in (*.mmd) do (
    set "name=%%~nF"
    rem skip if first char is "_"
    if /i not "!name:~0,1!"=="_" (
        echo Processing %%F
        call build_pdf.bat "%%F"
    )
)

endlocal
