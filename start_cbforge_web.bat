@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0start_cbforge_web.ps1" %*
exit /b %errorlevel%
