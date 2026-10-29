@echo off
set ROOT_DIR=%~dp0
"%ROOT_DIR%.venv\Scripts\python.exe" -m sac_mcp.cli %*
