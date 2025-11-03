# 🚀 Evidentia - Quick Start Guide

## One-Command Startup

Choose your preferred method to start both frontend and backend with a single command:

### **Option 1: NPM Script (Recommended - Cross-Platform)**

```bash
# First time only - install concurrently
npm install

# Start everything
npm run dev
```

This will start:
- ✅ Backend API on http://localhost:8000
- ✅ Frontend UI on http://localhost:3000

### **Option 2: PowerShell Script (Windows)**

```powershell
.\start.ps1
```

### **Option 3: Batch File (Windows - Simplest)**

```cmd
start.bat
```

Just double-click `start.bat` in Windows Explorer!

---

## 📋 Prerequisites

### Backend Requirements
- Python 3.9+
- Virtual environment (auto-created by scripts)

### Frontend Requirements
- Node.js 18+
- npm or yarn

---

## 🎯 First Time Setup

If this is your first time running Evidentia:

### 1. Install Backend Dependencies
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows
# or
source .venv/bin/activate    # Mac/Linux
pip install -r requirements.txt
cd ..
```

### 2. Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

### 3. Configure Environment
Create `frontend/.env.local`:
```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

### 4. Start Everything!
```bash
npm run dev
```

---

## 🌐 Access Points

Once running, access these URLs:

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend** | http://localhost:3000 | Main research interface |
| **Backend API** | http://localhost:8000 | FastAPI backend |
| **API Docs** | http://localhost:8000/docs | Interactive API documentation |
| **Health Check** | http://localhost:8000/health | Backend health status |

---

## 🔍 Test Your Setup

Try these research queries:

1. **"Latest developments in quantum computing"**
   - Tests: Web search, Wikipedia, arXiv papers

2. **"Climate change mitigation strategies"**
   - Tests: News sources, environmental sites, YouTube videos

3. **"Artificial intelligence in healthcare"**
   - Tests: Medical sources, academic papers, tech blogs

---

## 🛑 Stopping Services

### If using npm:
Press `Ctrl+C` in the terminal

### If using PowerShell script:
Press `Ctrl+C` in the terminal

### If using batch file:
Press any key in the command window

---

## 🐛 Troubleshooting

### Port Already in Use
If port 3000 or 8000 is already in use:

**Frontend:**
- Next.js will automatically use port 3001
- Or edit `frontend/package.json` to change the port

**Backend:**
- Edit the startup script to use a different port
- Update `NEXT_PUBLIC_API_BASE` in `frontend/.env.local`

### Backend Not Starting
```bash
# Check Python version
python --version  # Should be 3.9+

# Reinstall dependencies
cd backend
pip install -r requirements.txt
```

### Frontend Not Starting
```bash
# Clear cache and reinstall
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### "Failed to fetch" Error
- Make sure backend is running on port 8000
- Check `frontend/.env.local` has correct API URL
- Verify backend health: http://localhost:8000/health

---

## 📊 What Happens During Research

1. **Search Phase** (5-10 seconds)
   - Searches DuckDuckGo, Wikipedia, YouTube, arXiv
   - Finds 10-12 relevant sources

2. **Ingestion Phase** (10-20 seconds)
   - Downloads and extracts content
   - Processes HTML, PDFs, video transcripts

3. **Analysis Phase** (5-10 seconds)
   - Generates embeddings
   - Ranks content by relevance
   - Creates citations

4. **Report Generation** (2-5 seconds)
   - Structures findings
   - Generates comprehensive report
   - Links all evidence

**Total Time:** ~30-45 seconds per query

---

## 🎨 Features

- ✅ Multi-source search (Web, Wikipedia, YouTube, arXiv)
- ✅ Real-time progress tracking
- ✅ Evidence matrix with citations
- ✅ Beautiful glass-morphism UI
- ✅ Export to PDF/JSON
- ✅ Source attribution
- ✅ Responsive design

---

## 🚀 Production Deployment

For production deployment, see [DEPLOYMENT.md](./DEPLOYMENT.md)

---

## 📝 Development

### Backend Development
```bash
cd backend
python -m uvicorn app.main:app --reload
```

### Frontend Development
```bash
cd frontend
npm run dev
```

### Run Tests
```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

---

## 💡 Tips

1. **Faster Searches**: Reduce `maxSources` in the UI (default: 12)
2. **YouTube Videos**: Toggle "Include YouTube" for video content
3. **Recent Content**: Enable "Prefer recent" for latest information
4. **Export Reports**: Use PDF export for sharing findings

---

## 🤝 Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development guidelines.

---

## 📄 License

MIT License - See [LICENSE](./LICENSE) for details.

---

**Enjoy researching with Evidentia! 🎉**
