@echo off
cd /d %~dp0
if not exist logs mkdir logs
python collect.py --history-days 90 --delay 0.08 >> logs\refresh.log 2>&1
if errorlevel 1 exit /b 1
python build_site.py >> logs\refresh.log 2>&1
