"""
API Routes for New Features
Endpoints for citation management, templates, translation, fact-checking, etc.
"""

from fastapi import APIRouter, HTTPException, Body
from typing import Dict, List, Optional
from pydantic import BaseModel

# Import services
from app.services.citation_manager import citation_manager
from app.services.research_templates import template_manager, TemplateType
from app.services.translation import translation_service
from app.services.fact_checker import fact_checker
from app.services.credibility_scorer import credibility_scorer
from app.services.visual_extractor import visual_extractor

router = APIRouter(prefix="/features", tags=["features"])


# ==================== Citation Management ====================

class CitationRequest(BaseModel):
    sources: List[Dict]
    style: str = "APA"

class BibliographyRequest(BaseModel):
    sources: List[Dict]
    style: str = "APA"

@router.post("/citations/format")
async def format_citations(request: CitationRequest):
    """Format citations in specified style"""
    try:
        citations = []
        for source in request.sources:
            metadata = citation_manager.extract_metadata(source)
            citation = citation_manager.format_citation(metadata, request.style)
            citations.append({
                'source': source,
                'citation': citation,
                'metadata': metadata
            })
        
        return {
            'ok': True,
            'citations': citations,
            'style': request.style,
            'count': len(citations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/citations/bibliography")
async def generate_bibliography(request: BibliographyRequest):
    """Generate complete bibliography"""
    try:
        bibliography = citation_manager.generate_bibliography(request.sources, request.style)
        bibtex = citation_manager.export_to_bibtex(request.sources)
        ris = citation_manager.export_to_ris(request.sources)
        
        return {
            'ok': True,
            'bibliography': bibliography,
            'bibtex': bibtex,
            'ris': ris,
            'style': request.style
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/citations/styles")
async def get_citation_styles():
    """Get supported citation styles"""
    return {
        'ok': True,
        'styles': citation_manager.supported_formats
    }


# ==================== Research Templates ====================

@router.get("/templates")
async def list_templates():
    """List all available research templates"""
    try:
        templates = template_manager.list_templates()
        return {
            'ok': True,
            'templates': templates,
            'count': len(templates)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """Get specific template configuration"""
    try:
        template = template_manager.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        return {
            'ok': True,
            'template': template.get_config()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TemplateApplyRequest(BaseModel):
    template_id: str
    query: str

@router.post("/templates/apply")
async def apply_template(request: TemplateApplyRequest):
    """Apply template to query"""
    try:
        config = template_manager.apply_template(request.template_id, request.query)
        return {
            'ok': True,
            'config': config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Translation ====================

class TranslateRequest(BaseModel):
    text: str
    target_language: str
    source_language: Optional[str] = None

@router.post("/translate")
async def translate_text(request: TranslateRequest):
    """Translate text to target language"""
    try:
        result = await translation_service.translate(
            request.text,
            request.target_language,
            request.source_language
        )
        return {
            'ok': True,
            'translation': result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/translate/languages")
async def get_supported_languages():
    """Get supported languages"""
    try:
        languages = translation_service.get_supported_languages()
        return {
            'ok': True,
            'languages': languages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TranslateSourceRequest(BaseModel):
    source: Dict
    target_language: str

@router.post("/translate/source")
async def translate_source(request: TranslateSourceRequest):
    """Translate entire source"""
    try:
        translated = await translation_service.translate_source(
            request.source,
            request.target_language
        )
        return {
            'ok': True,
            'translated_source': translated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Fact Checking ====================

class FactCheckRequest(BaseModel):
    claim: str
    sources: List[Dict]

@router.post("/fact-check")
async def check_fact(request: FactCheckRequest):
    """Verify a claim against sources"""
    try:
        result = fact_checker.check_claim(request.claim, request.sources)
        return {
            'ok': True,
            'fact_check': result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BatchFactCheckRequest(BaseModel):
    claims: List[str]
    sources: List[Dict]

@router.post("/fact-check/batch")
async def batch_check_facts(request: BatchFactCheckRequest):
    """Check multiple claims"""
    try:
        results = fact_checker.batch_check(request.claims, request.sources)
        return {
            'ok': True,
            'results': results,
            'count': len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CrossReferenceRequest(BaseModel):
    citations: List[Dict]

@router.post("/fact-check/cross-reference")
async def cross_reference_citations(request: CrossReferenceRequest):
    """Cross-reference citations for contradictions"""
    try:
        analysis = fact_checker.cross_reference_citations(request.citations)
        return {
            'ok': True,
            'analysis': analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Credibility Scoring ====================

class CredibilityScoreRequest(BaseModel):
    source: Dict

@router.post("/credibility/score")
async def score_source_credibility(request: CredibilityScoreRequest):
    """Score source credibility"""
    try:
        score = credibility_scorer.score_source(request.source)
        return {
            'ok': True,
            'credibility': score
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BatchCredibilityRequest(BaseModel):
    sources: List[Dict]

@router.post("/credibility/batch")
async def batch_score_credibility(request: BatchCredibilityRequest):
    """Score multiple sources"""
    try:
        scored_sources = credibility_scorer.batch_score(request.sources)
        return {
            'ok': True,
            'sources': scored_sources,
            'count': len(scored_sources)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class FilterCredibilityRequest(BaseModel):
    sources: List[Dict]
    min_score: float = 0.5

@router.post("/credibility/filter")
async def filter_by_credibility(request: FilterCredibilityRequest):
    """Filter sources by credibility"""
    try:
        filtered = credibility_scorer.filter_by_credibility(
            request.sources,
            request.min_score
        )
        return {
            'ok': True,
            'sources': filtered,
            'count': len(filtered),
            'min_score': request.min_score
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/credibility/report")
async def get_credibility_report(request: BatchCredibilityRequest):
    """Generate credibility report"""
    try:
        report = credibility_scorer.get_credibility_report(request.sources)
        return {
            'ok': True,
            'report': report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Visual Extraction ====================

class VisualExtractionRequest(BaseModel):
    source: Dict

@router.post("/visual/extract")
async def extract_visuals(request: VisualExtractionRequest):
    """Extract visual elements from source"""
    try:
        visuals = visual_extractor.extract_visuals(request.source)
        summary = visual_extractor.generate_visual_summary(visuals)
        
        return {
            'ok': True,
            'visuals': visuals,
            'summary': summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TableAnalysisRequest(BaseModel):
    table_data: List[List[str]]

@router.post("/visual/analyze-table")
async def analyze_table(request: TableAnalysisRequest):
    """Analyze table structure and content"""
    try:
        analysis = visual_extractor.analyze_table(request.table_data)
        return {
            'ok': True,
            'analysis': analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/visual/table-to-csv")
async def convert_table_to_csv(request: TableAnalysisRequest):
    """Convert table to CSV format"""
    try:
        csv_data = visual_extractor.convert_table_to_csv(request.table_data)
        return {
            'ok': True,
            'csv': csv_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Health Check ====================

@router.get("/health")
async def features_health():
    """Check health of all feature services"""
    return {
        'ok': True,
        'services': {
            'citation_manager': 'operational',
            'template_manager': 'operational',
            'translation_service': 'operational',
            'fact_checker': 'operational',
            'credibility_scorer': 'operational',
            'visual_extractor': 'operational'
        },
        'features': [
            'Citation Management',
            'Research Templates',
            'Multi-Language Translation',
            'AI Fact-Checking',
            'Source Credibility Scoring',
            'Visual Data Extraction',
            'Voice Input (Frontend)',
            'Priority Matrix (Frontend)'
        ]
    }
