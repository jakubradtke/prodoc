@echo off
rem Build documents as PDF: build_pdf.bat [mmd2doc options] file.md ...
call "%~dp0build.bat" --fmt pdf %*
exit /b %ERRORLEVEL%
