@echo off
cd /d %~dp0
py -3 -m app.main run-all
pause
