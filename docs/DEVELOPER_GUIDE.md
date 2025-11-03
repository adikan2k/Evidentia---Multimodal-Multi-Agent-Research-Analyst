# 🛠️ Evidentia Developer Guide

Complete technical documentation for developers working on Evidentia.

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Setup & Installation](#setup--installation)
3. [Feature Implementation](#feature-implementation)
4. [Testing Guide](#testing-guide)
5. [Deployment](#deployment)
6. [Troubleshooting](#troubleshooting)

---

## 🏗️ Architecture Overview

### System Components

```
Frontend (Next.js) → API (FastAPI) → Services → Data Layer
```

### Data Flow

1. **User Input** → Frontend captures query (text or voice)
2. **Query Planning** → LangGraph decomposes into sub-queries
3. **Source Discovery** → Search generates URLs for ingestion
4. **Multi-Source Ingest** → HTML, PDF, YouTube processed in parallel
5. **Embedding** → BGE-large-en generates vectors
6. **Vector Search** → Qdrant finds relevant passages
7. **Reranking** → BGE-reranker sorts by relevance
8. **Report Generation** → Hackathon Writer creates query-specific report
9. **Export** → PDF/JSON/CSV formats available

### Key Technologies

- **Frontend**: Next.js 15, React 18, TailwindCSS, shadcn/ui
- **Backend**: FastAPI, Python 3.11+
- **AI/ML**: Sentence Transformers, BGE models, LangGraph
- **Database**: PostgreSQL (metadata), Qdrant (vectors)
- **Storage**: MinIO (S3-compatible)
- **Cache**: Valkey (Redis-compatible)

---

## ⚙️ Setup & Installation

### Prerequisites

```bash
# Check versions
python --version  # 3.11+
node --version    # 18+
docker --version  # 20+
```

### Full Setup

```bash
# 1. Clone repository
git clone <repo-url>
cd Evidentia---Multimodal-Multi-Agent-Research-Analyst-

# 2. Backend setup
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 3. Frontend setup
cd ../frontend
npm install
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local

# 4. Infrastructure
cd ../ops
docker compose up -d

# 5. Start services
# Terminal 1: Backend
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload

# Terminal 2: Frontend
cd frontend && npm run dev
```

---

## 🎯 Feature Implementation

### 1. Hackathon Writer (Zero Generic Content)

**File**: `backend/app/services/hackathon_writer.py`

**Key Principles**:
- Every sentence must be query-specific
- Extract real evidence from sources
- No template text or generic phrases
- Confidence scores based on actual data

**Example**:
```python
# ❌ Generic (bad)
"This research examines multiple dimensions of the topic."

# ✅ Specific (good)
"This research examines 'GPT-2 capabilities', analyzing 6 sources 
and identifying 5 core themes: generation, language, model, training, parameters."
```

### 2. Voice Input

**Files**: 
- `frontend/src/components/ui/voice-input.tsx`
- `frontend/src/app/page.tsx`

**Features**:
- Web Speech API integration
- Continuous listening mode
- Error handling for permissions
- Browser compatibility checks

### 3. Keyboard Shortcuts

**Files**:
- `frontend/src/hooks/useKeyboardShortcuts.ts`
- `frontend/src/components/ui/shortcuts-modal.tsx`

**Shortcuts**:
```typescript
Ctrl + K     → Focus search
Ctrl + Enter → Start research
Ctrl + /     → Show shortcuts
Ctrl + S     → Save report
Ctrl + E     → Export PDF
```

### 4. Query Suggestions

**File**: `frontend/src/components/ui/query-suggestions.tsx`

**Structure**:
```typescript
const EXAMPLE_QUERIES = [
  {
    category: "Technology",
    icon: Code,
    color: "blue",
    queries: ["GPT-4 vs Claude 3...", ...]
  },
  // ...
];
```

### 5. PDF Export

**File**: `frontend/src/lib/export-pdf.ts`

**Implementation**:
- Client-side generation with jsPDF
- Extracts query from report HTML
- Formats sections with proper styling
- Adds pagination and headers

---

## 🧪 Testing Guide

### Unit Tests

```bash
# Backend
cd backend
pytest tests/

# Frontend
cd frontend
npm test
```

### Manual Testing Checklist

#### Voice Input
- [ ] Click mic button
- [ ] Grant microphone permissions
- [ ] Speak query
- [ ] Verify text appears
- [ ] Click again to stop

#### Keyboard Shortcuts
- [ ] Press Ctrl + /
- [ ] Modal appears with shortcuts list
- [ ] Press Ctrl + K
- [ ] Focus moves to search
- [ ] Press Ctrl + Enter
- [ ] Research starts

#### Query Suggestions
- [ ] Visit homepage
- [ ] See 4 category cards
- [ ] Click any query
- [ ] Query fills search box
- [ ] Suggestions disappear

#### PDF Export
- [ ] Complete a research
- [ ] Click "Export PDF"
- [ ] PDF downloads
- [ ] Open PDF
- [ ] Verify formatting

#### Comparative Analysis
- [ ] Query: "Python vs JavaScript"
- [ ] Start research
- [ ] Wait for completion
- [ ] Check report has comparison table
- [ ] Verify 7 aspects compared
- [ ] Check key differences listed

### Example Test Queries

```
✅ "GPT-4 vs Claude 3 Opus for coding"
✅ "AI trends 2024"
✅ "Python vs JavaScript for web development"
✅ "Type 1 vs Type 2 diabetes treatment"
✅ "Climate change solutions that work"
```

---

## 🚀 Deployment

### Development

```bash
npm run dev
```

### Production

#### Frontend (Vercel)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
cd frontend
vercel --prod
```

#### Backend (Railway)

```bash
# Install Railway CLI
npm i -g @railway/cli

# Deploy
cd backend
railway up
```

#### Docker

```bash
# Build
docker compose -f docker-compose.prod.yml build

# Deploy
docker compose -f docker-compose.prod.yml up -d
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Voice Input Not Working

**Problem**: Mic button doesn't respond

**Solutions**:
- Check browser permissions
- Try Chrome/Edge (best support)
- Reload page and try again
- Check console for errors

#### 2. Keyboard Shortcuts Not Working

**Problem**: Shortcuts don't trigger

**Solutions**:
- Check if focus is in input field
- Try Cmd instead of Ctrl on Mac
- Clear browser cache
- Verify imports are correct

#### 3. PDF Export Fails

**Problem**: PDF doesn't download

**Solutions**:
- Check browser pop-up blocker
- Verify report HTML is loaded
- Check console for errors
- Try different browser

#### 4. Docker Services Won't Start

**Problem**: `docker compose up` fails

**Solutions**:
```bash
# Check Docker is running
docker ps

# Remove old containers
docker compose down -v

# Rebuild
docker compose up -d --build

# Check logs
docker compose logs
```

#### 5. Frontend Can't Connect to Backend

**Problem**: Network errors in console

**Solutions**:
- Verify backend is running on port 8000
- Check `.env.local` has correct API URL
- Check for CORS issues
- Restart both services

### Debug Commands

```bash
# Check all services
docker compose ps

# View logs
docker compose logs -f

# Check backend health
curl http://localhost:8000/health

# Check Qdrant
curl http://localhost:6333/collections

# Check MinIO
curl http://localhost:9000/minio/health/live
```

---

## 📝 Code Style Guide

### Python

```python
# Use type hints
def ingest_url(url: str) -> List[Dict[str, Any]]:
    pass

# Use docstrings
def process_text(text: str) -> str:
    """
    Process and clean input text.
    
    Args:
        text: Raw text to process
        
    Returns:
        Cleaned text string
    """
    pass

# Use Black for formatting
black backend/
```

### TypeScript/React

```typescript
// Use TypeScript interfaces
interface VoiceInputProps {
  onTranscript: (text: string) => void;
  language?: string;
}

// Use functional components
export function VoiceInput({ onTranscript, language }: VoiceInputProps) {
  // Component code
}

// Use hooks
const [isListening, setIsListening] = useState(false);
```

---

## 🔧 Adding New Features

### 1. New Source Type

```bash
# 1. Create ingestion module
backend/app/ingest/newsource.py

# 2. Implement ingest function
def ingest_url(url: str) -> List[Dict]:
    # Extract content
    return passages

# 3. Register in factory
backend/app/ingest/factory.py

# 4. Add tests
backend/tests/test_newsource.py
```

### 2. New UI Component

```bash
# 1. Create component
frontend/src/components/ui/newcomp.tsx

# 2. Add styling
Use TailwindCSS classes

# 3. Export from index
frontend/src/components/ui/index.ts

# 4. Use in page
import { NewComp } from "@/components/ui/newcomp"
```

### 3. New API Endpoint

```python
# backend/app/api/routes/newroute.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/new-endpoint")
async def new_endpoint():
    return {"message": "Hello"}

# Register in main.py
app.include_router(newroute.router, prefix="/api")
```

---

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [LangGraph Docs](https://python.langchain.com/docs/langgraph)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [shadcn/ui Components](https://ui.shadcn.com/)

---

## 🤝 Contributing

See the main [README.md](../README.md#contributing) for contribution guidelines.

---

## 📞 Support

- GitHub Issues: Report bugs and request features
- Documentation: This guide and README.md
- Code Comments: Inline documentation in source files

---

**Last Updated**: November 2024  
**Version**: 1.1.0

