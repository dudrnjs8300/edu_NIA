@echo off
cd /d %~dp0
py -3 -m py_compile app\gui.py app\main.py app\pipeline.py app\config.py app\llm_client.py
if errorlevel 1 goto :end
py -3 -m app.main init
if errorlevel 1 goto :end
py -3 -m app.main run-all
if errorlevel 1 goto :end
py -3 -c "import json; json.load(open('workspace/02_education_processed/education_concepts.json', encoding='utf-8')); print('education_concepts OK')"
if errorlevel 1 goto :end
py -3 -c "import json; json.load(open('workspace/05_department_analysis/department_work_map.json', encoding='utf-8')); print('department_work_map OK')"
if errorlevel 1 goto :end
py -3 -c "import json; json.load(open('workspace/06_matching_output/idea_cards.json', encoding='utf-8')); print('idea_cards OK')"
:end
pause
