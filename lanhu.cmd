@echo off
rem lanhu CLI shim: run lanhu_cli.py with repo venv python, pass args through
set "PYTHONIOENCODING=utf-8"
"%~dp0venv\Scripts\python.exe" "%~dp0lanhu_cli.py" %*
