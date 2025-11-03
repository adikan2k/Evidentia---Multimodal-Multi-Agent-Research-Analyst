<div align="center">

# 🔬 Evidentia

### AI-Powered Research Assistant for Evidence-Based Analysis

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**[Features](#-features) • [Quick Start](#-quick-start) • [Demo](#-demo) • [Documentation](#-architecture) • [Contributing](#-contributing)**

**Created by**: [Aditya Kanbargi](https://github.com/adikan2k) & [Sanjana Kadambe Muralidhar](https://github.com/sanjanakadambe)

</div>

---

## 📖 Overview

**Evidentia** is a cutting-edge AI research assistant that transforms how you conduct research. It analyzes multiple sources simultaneously, extracts insights, generates professional reports, and provides **zero generic content** - every sentence is backed by real evidence.

### ✨ What Makes Evidentia Special

- 🎯 **Zero Generic Content** - Every sentence is specific and evidence-based
- 🎤 **Voice-First Design** - Speak your queries naturally
- ⚡ **Lightning Fast** - Analyze 10+ sources in under 60 seconds
- 🔍 **Multi-Source Intelligence** - Web, PDFs, videos, images
- 🤖 **Multi-Agent System** - Advanced RAG architecture
- 📊 **Professional Reports** - Export to PDF, JSON, CSV
- ♿ **Accessible** - Keyboard shortcuts & voice input
- 🎨 **Beautiful UI** - Modern glass morphism design

---

## 🎯 Key Features

### 🔬 Research Intelligence
- **Advanced RAG Architecture** - Retrieval-Augmented Generation for accuracy
- **Multi-Agent System** - Parallel source analysis and verification
- **Automatic Fact-Checking** - Cross-reference validation
- **Semantic Search** - BGE embeddings + Qdrant vector database
- **Smart Reranking** - BGE-reranker for relevance

### 📚 Multi-Source Analysis
- **Web Pages** - HTML extraction and analysis
- **PDFs** - Text, OCR, and table extraction
- **Videos** - YouTube transcript processing
- **Images** - OCR with Tesseract
- **Multimodal** - Figure captioning with BLIP-2

### 🎨 User Experience
- **Voice Input** - Speak your research queries
- **Keyboard Shortcuts** - Power user productivity (`Ctrl+K`, `Ctrl+Enter`)
- **Query Suggestions** - 16 curated examples across 4 categories
- **Real-Time Progress** - Live visualization of research process
- **Export Options** - PDF (client-side), JSON, CSV

### 🏆 Hackathon-Winning Features
- **Zero Generic Content Engine** - Every word is query-specific
- **Evidence-Based Reports** - All claims backed by sources
- **Confidence Scores** - Transparent reliability metrics
- **Comparative Analysis** - Side-by-side comparisons with tables
- **Professional Styling** - Publication-ready reports

---

## ⚡ Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose

### 🚀 Fastest Setup (3 Steps)

```bash
# 1. Install root dependencies (first time only)
npm install

# 2. Start all services
npm run dev

# 3. Open your browser
http://localhost:3000
```

**That's it!** 🎉

### Alternative Startup Methods

<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
.\start.ps1
```
</details>

<details>
<summary><b>Windows Batch (Double-Click)</b></summary>

Just double-click `start.bat` in the root folder!
</details>

<details>
<summary><b>Manual Setup</b></summary>

```bash
# Terminal 1 - Backend
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload

# Terminal 2 - Frontend
cd frontend
npm install
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
npm run dev

# Terminal 3 - Services
cd ops
docker compose up -d
```
</details>

---

## 🎬 Demo

### Try These Example Queries

```
🔬 "GPT-4 vs Claude 3 Opus for coding assistance"
📊 "AI trends and predictions for 2024"
🏥 "Compare type 1 and type 2 diabetes treatments"
💻 "Python vs JavaScript for web development"
🌍 "Climate change solutions that actually work"
```

### What Happens

1. **Analysis** (30-60s)
   - Discovers 10+ relevant sources
   - Extracts and embeds content
   - Performs semantic search
   - Cross-references facts

2. **Report Generation** (10s)
   - Generates query-specific insights
   - Creates comparison tables (for "vs" queries)
   - Extracts statistics and data
   - Provides decision guidance

3. **Export & Share**
   - Download as professional PDF
   - Export raw data as JSON
   - Share via unique link

### Keyboard Shortcuts ⌨️

- `Ctrl + K` - Focus search
- `Ctrl + Enter` - Start research
- `Ctrl + /` - Show all shortcuts
- `Ctrl + S` - Save report (coming soon)
- `Ctrl + E` - Export PDF

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│  Next.js 15 + React + TailwindCSS + shadcn/ui               │
│  Voice Input | Keyboard Shortcuts | Query Suggestions       │
└────────────────────────┬────────────────────────────────────┘
                         │ REST API
┌────────────────────────┴────────────────────────────────────┐
│                     Backend (FastAPI)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Planner    │  │   Ingest     │  │    Writer    │     │
│  │  (LangGraph) │→ │ Multi-source │→ │ Hackathon    │     │
│  │  Sub-queries │  │   Pipeline   │  │   Writer     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────────┐
│                    Data Layer (Docker)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Qdrant     │  │  PostgreSQL  │  │    MinIO     │     │
│  │   Vectors    │  │   Metadata   │  │   Storage    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### Tech Stack

<table>
<tr>
<td>

**Frontend**
- Next.js 15
- React 18
- TailwindCSS
- shadcn/ui
- Radix UI
- Lucide Icons
- jsPDF

</td>
<td>

**Backend**
- Python 3.11+
- FastAPI
- LangGraph
- Sentence Transformers
- Tesseract OCR
- BLIP-2
- BeautifulSoup

</td>
<td>

**Infrastructure**
- Docker Compose
- Qdrant (vectors)
- PostgreSQL
- MinIO (S3)
- Valkey (cache)
- Prometheus

</td>
</tr>
</table>

### Project Structure

```bash
Evidentia/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routes
│   │   ├── ingest/           # Multi-source ingestion
│   │   │   ├── html.py       # Web scraping
│   │   │   ├── pdf.py        # PDF + OCR
│   │   │   ├── youtube.py    # Video transcripts
│   │   │   └── factory.py    # Source routing
│   │   ├── services/
│   │   │   ├── advanced_writer.py    # Original writer
│   │   │   ├── hackathon_writer.py   # Zero-generic writer
│   │   │   ├── embedding.py          # BGE embeddings
│   │   │   └── reranker.py           # BGE reranker
│   │   ├── planner/          # LangGraph query planning
│   │   ├── graph/            # Pipeline orchestration
│   │   └── main.py           # FastAPI app
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/              # Next.js pages
│   │   │   ├── page.tsx              # Homepage
│   │   │   └── research/
│   │   │       ├── progress/         # Live progress
│   │   │       └── report/           # Results
│   │   ├── components/ui/    # React components
│   │   │   ├── voice-input.tsx       # Voice search
│   │   │   ├── shortcuts-modal.tsx   # Keyboard help
│   │   │   └── query-suggestions.tsx # Query examples
│   │   ├── hooks/
│   │   │   └── useKeyboardShortcuts.ts
│   │   └── lib/
│   │       └── export-pdf.ts         # PDF generation
│   └── package.json
├── ops/
│   └── docker-compose.yml    # Infrastructure
├── docs/
│   └── DEVELOPER_GUIDE.md    # Full documentation
└── README.md                 # You are here!
```

---

## 🔌 API Endpoints

### Research
```http
POST /research/start
GET  /research/status?jobId={id}
GET  /research/report?jobId={id}
```

### Export
```http
POST /export/pdf
GET  /export/json?jobId={id}
GET  /export/csv?jobId={id}
```

### Management
```http
GET    /maintenance/runs
DELETE /maintenance/delete-run/{jobId}
GET    /metrics
GET    /health
```

### Full API Documentation
**Swagger UI**: http://localhost:8000/docs  
**ReDoc**: http://localhost:8000/redoc

---

## ⚙️ Configuration

### Backend Environment Variables

```bash
# Database
PG_URL=postgresql://user:pass@localhost:5432/evidentia

# Vector Store
QDRANT_URL=http://localhost:6333

# Object Storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Cache
VALKEY_URL=redis://localhost:6379
```

### Frontend Environment Variables

```bash
# .env.local
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

---

## 🛠️ Development

### Adding New Features

<details>
<summary><b>Add New Source Type</b></summary>

1. Create ingestion module: `backend/app/ingest/newsource.py`
2. Implement `ingest_url(url: str) -> List[Dict]`
3. Register in `backend/app/ingest/factory.py`
4. Test with unit tests
</details>

<details>
<summary><b>Customize Report Writer</b></summary>

1. Edit `backend/app/services/hackathon_writer.py`
2. Modify `generate_report()` method
3. Update section generation functions
4. Test with sample queries
</details>

<details>
<summary><b>Add UI Components</b></summary>

1. Create component: `frontend/src/components/ui/newcomp.tsx`
2. Import in page: `import { NewComp } from "@/components/ui/newcomp"`
3. Use TailwindCSS for styling
4. Follow shadcn/ui patterns
</details>

### Testing

```bash
# Backend tests
cd backend
pytest tests/

# Frontend tests
cd frontend
npm test

# E2E tests
npm run test:e2e
```

### Code Quality

```bash
# Backend
black backend/
flake8 backend/
mypy backend/

# Frontend
npm run lint
npm run format
```

---

## 🚀 Deployment

### Local Development
✅ Already running! (see Quick Start)

### Production Deployment

<table>
<tr>
<th>Service</th>
<th>Recommended Platform</th>
<th>Notes</th>
</tr>
<tr>
<td>Frontend</td>
<td>Vercel / Netlify</td>
<td>Zero-config Next.js deployment</td>
</tr>
<tr>
<td>Backend</td>
<td>Railway / Render</td>
<td>Auto-deploy from GitHub</td>
</tr>
<tr>
<td>Database</td>
<td>Neon / Supabase</td>
<td>Managed PostgreSQL</td>
</tr>
<tr>
<td>Vectors</td>
<td>Qdrant Cloud</td>
<td>Managed vector database</td>
</tr>
<tr>
<td>Storage</td>
<td>AWS S3 / Cloudflare R2</td>
<td>Object storage</td>
</tr>
</table>

### Docker Deployment

```bash
# Build images
docker compose -f docker-compose.prod.yml build

# Deploy stack
docker compose -f docker-compose.prod.yml up -d

# Scale workers
docker compose scale backend=3
```

---

## 🤝 Contributing

We love contributions! Here's how you can help:

### Ways to Contribute

- 🐛 **Report Bugs** - Open an issue with details
- 💡 **Suggest Features** - Share your ideas
- 📝 **Improve Docs** - Fix typos, add examples
- 🔧 **Submit PRs** - Fix bugs or add features
- ⭐ **Star the Repo** - Show your support!

### Development Setup

1. **Fork the repository**
2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR_USERNAME/evidentia.git
   cd evidentia
   ```
3. **Create a branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```
4. **Make your changes**
5. **Test thoroughly**
6. **Commit with clear messages**
   ```bash
   git commit -m "feat: add amazing feature"
   ```
7. **Push and create PR**
   ```bash
   git push origin feature/amazing-feature
   ```

### Code Style

- **Python**: Follow PEP 8, use type hints
- **TypeScript**: Follow Airbnb style guide
- **Commits**: Use [Conventional Commits](https://www.conventionalcommits.org/)

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **OpenAI** - For inspiration
- **LangChain/LangGraph** - Graph-based orchestration
- **Hugging Face** - BGE embeddings and models
- **Vercel** - Next.js framework
- **shadcn/ui** - Beautiful component library
- **All Contributors** - Thank you! 🎉

---

## 📞 Support

- 📧 **Email**: support@evidentia.dev (coming soon)
- 💬 **Discord**: [Join our community](https://discord.gg/evidentia) (coming soon)
- 🐦 **Twitter**: [@EvidentiaDev](https://twitter.com/EvidentiaDev) (coming soon)
- 📖 **Documentation**: [Full Developer Guide](docs/DEVELOPER_GUIDE.md)

---

## 🌟 Star History

If you find Evidentia useful, please consider starring the repo! ⭐

---

## 🗺️ Roadmap

### v1.1 (Current)
- [x] Voice input
- [x] Keyboard shortcuts
- [x] Query suggestions
- [x] PDF export
- [x] Zero generic content

### v1.2 (Next)
- [ ] Knowledge graph visualization
- [ ] Dark/light mode toggle
- [ ] Research history
- [ ] Collaborative features
- [ ] Mobile app (React Native)

### v2.0 (Future)
- [ ] LLM integration (GPT-4, Claude)
- [ ] Custom AI models
- [ ] Browser extension
- [ ] API for developers
- [ ] Enterprise features

---

<div align="center">

### 👥 Created By

**Aditya Kanbargi** & **Sanjana Kadambe Muralidhar**

---

### Built with ❤️ for researchers, students, and knowledge seekers everywhere

**[⬆ Back to Top](#-evidentia)**

© 2024 Evidentia by Aditya Kanbargi & Sanjana Kadambe Muralidhar. All rights reserved.

</div>
