@echo off

echo Starting CMDB Application...
echo ================================

rem 启动FastAPI服务器
echo Starting server...
.conda-py311\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
