#!/bin/bash
echo "🛑 Stopping services..."
pkill -f streamlit
pkill -f uvicorn
sleep 2

echo "🚀 Starting FastAPI..."
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > fastapi.log 2>&1 &
echo "FastAPI PID: $!"
sleep 2

echo "🚀 Starting Streamlit..."
nohup streamlit run app/frontend/app.py > streamlit.log 2>&1 &
echo "Streamlit PID: $!"
sleep 3

echo ""
echo "✅ Services started!"
echo "FastAPI:   http://140.238.10.51:8000"
echo "Streamlit: http://140.238.10.51:8501"
echo ""

ps aux | grep -E "streamlit|uvicorn" | grep -v grep
