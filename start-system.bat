@echo off
title AI-Based Sales Forecasting System

cd /d "%~dp0"

echo Starting the system...
echo Open http://127.0.0.1:5001 in your browser.
echo Keep this window open while using the system.
echo.

".venv\Scripts\python.exe" -m flask --app app run --port 5001

pause