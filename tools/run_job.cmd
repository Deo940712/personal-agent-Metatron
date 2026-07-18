@echo off
rem MY AGENT job runner(Task Scheduler 用;參數 = job 名)
rem 用法:run_job.cmd remind
cd /d "%~dp0.."
set LOGDIR=C:\Users\tcart\my-agent-data\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
echo [%date% %time%] --job %1 start >> "%LOGDIR%\%1.log"
"C:\Users\tcart\anaconda3\python.exe" -m core.agent --job %1 >> "%LOGDIR%\%1.log" 2>&1
echo [%date% %time%] --job %1 exit %errorlevel% >> "%LOGDIR%\%1.log"
