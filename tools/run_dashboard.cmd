@echo off
rem Metatron dashboard launcher (read-only web UI on 127.0.0.1:7777).
cd /d "%~dp0.."
"C:\Users\tcart\anaconda3\python.exe" -X utf8 -m channels.dashboard
