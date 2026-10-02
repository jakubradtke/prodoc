@echo off
rem Build every document under a folder: *.md and *.mmd, except chapters starting with "_"
rem and files in auto\ folders.
rem Usage: build_all.bat [html^|docx^|pdf] [folder]    (default: html, current folder)
rem Exit code: 0 = all built, 1 = at least one document failed, 2 = folder not found.
setlocal EnableExtensions DisableDelayedExpansion

set "HERE=%~dp0"
set "FMT=html"
set "ROOT=%CD%"

:args
if "%~1"=="" goto :start
if /i "%~1"=="html" (set "FMT=html" & shift & goto :args)
if /i "%~1"=="docx" (set "FMT=docx" & shift & goto :args)
if /i "%~1"=="pdf" (set "FMT=pdf" & shift & goto :args)
set "ROOT=%~f1"
shift
goto :args

:start
if not exist "%ROOT%\" goto :noroot
set "COUNT=0"
set "FAILED=0"
set "FAILED_LIST=%TEMP%\prodoc_failed_%RANDOM%%RANDOM%.txt"
if exist "%FAILED_LIST%" del "%FAILED_LIST%"

echo.
echo ==============================
echo   PRODOC %FMT% build started %DATE% %TIME%
echo   %ROOT%
echo ==============================
echo.

rem A subroutine per file keeps names with "!" intact (no delayed expansion)
for %%E in (mmd md) do for /r "%ROOT%" %%F in (*.%%E) do call :one "%%F"

echo.
if %COUNT% EQU 0 (
    echo No .mmd or .md files found to process.
) else (
    echo Processed %COUNT% file^(s^), failed %FAILED%.
)
if exist "%FAILED_LIST%" (
    echo Failed documents:
    type "%FAILED_LIST%"
    del "%FAILED_LIST%"
)
echo ==============================
echo   PRODOC %FMT% build finished %DATE% %TIME%
echo ==============================

if %FAILED% GTR 0 exit /b 1
exit /b 0

:one
set "NAME=%~n1"
if "%NAME:~0,1%"=="_" exit /b 0
set "DIR=%~dp1"
if /i not "%DIR:\auto\=%"=="%DIR%" exit /b 0
set /a COUNT+=1
echo [%COUNT%] %~n1: %~1
call "%HERE%build.bat" --fmt %FMT% "%~1"
rem No parenthesised block here: a ")" in the document path would break it
if not errorlevel 1 exit /b 0
set /a FAILED+=1
>>"%FAILED_LIST%" echo   %~1
echo FAILED: %~1
exit /b 0

:noroot
echo ERROR: folder not found: %ROOT%
exit /b 2
