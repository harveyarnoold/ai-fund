@echo off
cd C:\Users\bigha\ai_fund
call .venv\Scripts\activate
python orchestrator.py >> logs\pipeline_log.txt 2>&1