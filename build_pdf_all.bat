@echo off
rem Build every document under a folder as PDF: build_pdf_all.bat [folder]
call "%~dp0build_all.bat" pdf %*
exit /b %ERRORLEVEL%
