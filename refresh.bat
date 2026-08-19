@echo off
cd /d %~dp0
python collect.py
if errorlevel 1 exit /b 1
python build_site.py
