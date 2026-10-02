@echo off
rem Build every document under a folder as DOCX: build_docx_all.bat [folder]
call "%~dp0build_all.bat" docx %*
exit /b %ERRORLEVEL%
