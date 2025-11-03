#!/bin/bash
# Evidentia 90-second demo script for localhost

set -e

echo "🚀 Starting Evidentia demo stack..."

# Start Docker Compose services
cd ops
docker compose up -d
echo "⏳ Waiting for services to be healthy..."
sleep 45

# Start backend (assumes venv already created)
cd ../backend
source .venv/bin/activate || { echo "❌ Backend venv not found. Run 'python -m venv .venv && pip install -r requirements.txt' first."; exit 1; }
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "✅ Backend started (PID $BACKEND_PID)"

# Start frontend
cd ../frontend
npm run dev &
FRONTEND_PID=$!
echo "✅ Frontend started (PID $FRONTEND_PID)"

echo ""
echo "🌐 Open your browser to: http://localhost:3000"
echo "📌 Try this query: 'Compare GLP-1 vs SGLT2 outcomes in T2D'"
echo "📊 Watch the progress, then view the Evidence Matrix and export PDF."
echo ""
echo "Press Ctrl+C to stop all services."

# Wait for interrupt
trap "echo '🛑 Stopping services...'; kill $BACKEND_PID $FRONTEND_PID; cd ../ops && docker compose down; exit 0" INT
wait
