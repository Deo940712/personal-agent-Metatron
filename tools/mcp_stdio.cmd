@echo off
rem Metatron MCP stdio launcher for OpenCode (fixes cwd + module path).
rem Point the OpenCode MCP command at this file; works from any spawn cwd.
cd /d "%~dp0.."
"C:\Users\tcart\anaconda3\python.exe" -X utf8 -m channels.mcp_stdio
