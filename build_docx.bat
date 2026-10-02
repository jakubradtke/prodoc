@echo off
rem Build documents as DOCX: build_docx.bat [mmd2doc options] file.md ...
call "%~dp0build.bat" --fmt docx %*
exit /b %ERRORLEVEL%
