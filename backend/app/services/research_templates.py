"""
Research Templates System
Pre-built templates for different research types with optimized parameters
"""

from typing import Dict, List, Optional
from enum import Enum


class TemplateType(str, Enum):
    """Available research template types"""
    LITERATURE_REVIEW = "literature_review"
    MARKET_RESEARCH = "market_research"
    COMPETITIVE_ANALYSIS = "competitive_analysis"
    TECHNICAL_DEEP_DIVE = "technical_deep_dive"
    TREND_ANALYSIS = "trend_analysis"
    FACT_CHECK = "fact_check"
    ACADEMIC_RESEARCH = "academic_research"
    BUSINESS_INTELLIGENCE = "business_intelligence"


class ResearchTemplate:
    """Base class for research templates"""
    
    def __init__(self, name: str, description: str, icon: str):
        self.name = name
        self.description = description
        self.icon = icon
        self.parameters = {}
        self.prompt_template = ""
        self.output_format = {}
    
    def get_config(self) -> Dict:
        """Get template configuration"""
        return {
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'parameters': self.parameters,
            'prompt_template': self.prompt_template,
            'output_format': self.output_format
        }


class LiteratureReviewTemplate(ResearchTemplate):
    """Template for academic literature reviews"""
    
    def __init__(self):
        super().__init__(
            name="Literature Review",
            description="Comprehensive review of academic literature on a topic",
            icon="📚"
        )
        self.parameters = {
            'maxSources': 20,
            'includeYoutube': False,
            'includeAcademic': True,
            'minPublicationYear': 2015,
            'sortBy': 'citations',
            'includeMetaAnalysis': True
        }
        self.prompt_template = """
Conduct a comprehensive literature review on: {query}

Focus on:
1. Key theories and frameworks
2. Major findings and consensus
3. Gaps in current research
4. Methodological approaches
5. Future research directions

Prioritize peer-reviewed sources and recent publications.
"""
        self.output_format = {
            'sections': [
                'Introduction',
                'Theoretical Framework',
                'Key Findings',
                'Research Gaps',
                'Methodology Review',
                'Conclusions',
                'References'
            ]
        }


class MarketResearchTemplate(ResearchTemplate):
    """Template for market research and analysis"""
    
    def __init__(self):
        super().__init__(
            name="Market Research",
            description="Analyze market trends, size, and opportunities",
            icon="📊"
        )
        self.parameters = {
            'maxSources': 15,
            'includeYoutube': True,
            'includeNews': True,
            'includeReports': True,
            'timeRange': '1year',
            'includeStatistics': True
        }
        self.prompt_template = """
Conduct market research on: {query}

Analyze:
1. Market size and growth rate
2. Key players and market share
3. Customer segments and demographics
4. Trends and opportunities
5. Challenges and barriers
6. Future outlook

Include quantitative data where available.
"""
        self.output_format = {
            'sections': [
                'Executive Summary',
                'Market Overview',
                'Market Size & Growth',
                'Competitive Landscape',
                'Customer Analysis',
                'Trends & Opportunities',
                'Recommendations'
            ]
        }


class CompetitiveAnalysisTemplate(ResearchTemplate):
    """Template for competitive analysis"""
    
    def __init__(self):
        super().__init__(
            name="Competitive Analysis",
            description="Analyze competitors, strengths, and market position",
            icon="🎯"
        )
        self.parameters = {
            'maxSources': 18,
            'includeYoutube': True,
            'includeSocialMedia': True,
            'includeFinancials': True,
            'compareFeatures': True
        }
        self.prompt_template = """
Conduct competitive analysis for: {query}

Compare:
1. Key competitors and market position
2. Products/services comparison
3. Pricing strategies
4. Strengths and weaknesses (SWOT)
5. Marketing approaches
6. Customer reviews and sentiment
7. Unique value propositions

Provide actionable insights.
"""
        self.output_format = {
            'sections': [
                'Competitive Landscape',
                'Competitor Profiles',
                'Feature Comparison',
                'SWOT Analysis',
                'Market Positioning',
                'Strategic Recommendations'
            ]
        }


class TechnicalDeepDiveTemplate(ResearchTemplate):
    """Template for technical deep dives"""
    
    def __init__(self):
        super().__init__(
            name="Technical Deep Dive",
            description="In-depth technical analysis and documentation",
            icon="🔬"
        )
        self.parameters = {
            'maxSources': 25,
            'includeYoutube': True,
            'includeGithub': True,
            'includeDocumentation': True,
            'includeTutorials': True,
            'technicalDepth': 'advanced'
        }
        self.prompt_template = """
Conduct technical deep dive on: {query}

Cover:
1. Technical architecture and design
2. Implementation details
3. Best practices and patterns
4. Performance considerations
5. Security implications
6. Common pitfalls and solutions
7. Code examples and tutorials
8. Tools and ecosystem

Target audience: Technical professionals.
"""
        self.output_format = {
            'sections': [
                'Overview',
                'Architecture',
                'Implementation Guide',
                'Best Practices',
                'Performance & Security',
                'Troubleshooting',
                'Resources & Tools'
            ]
        }


class TrendAnalysisTemplate(ResearchTemplate):
    """Template for trend analysis"""
    
    def __init__(self):
        super().__init__(
            name="Trend Analysis",
            description="Identify and analyze emerging trends",
            icon="📈"
        )
        self.parameters = {
            'maxSources': 20,
            'includeYoutube': True,
            'includeNews': True,
            'includeSocialMedia': True,
            'timeRange': '6months',
            'includeForecasts': True
        }
        self.prompt_template = """
Analyze trends for: {query}

Identify:
1. Current trends and patterns
2. Emerging developments
3. Growth trajectories
4. Driving factors
5. Industry impact
6. Future predictions
7. Regional variations

Focus on recent developments (last 6-12 months).
"""
        self.output_format = {
            'sections': [
                'Trend Overview',
                'Current State',
                'Emerging Patterns',
                'Driving Forces',
                'Impact Analysis',
                'Future Outlook',
                'Recommendations'
            ]
        }


class FactCheckTemplate(ResearchTemplate):
    """Template for fact-checking claims"""
    
    def __init__(self):
        super().__init__(
            name="Fact Check",
            description="Verify claims with multiple authoritative sources",
            icon="✓"
        )
        self.parameters = {
            'maxSources': 12,
            'includeYoutube': False,
            'requireMultipleSources': True,
            'prioritizeAuthority': True,
            'crossReference': True,
            'includeOriginalSource': True
        }
        self.prompt_template = """
Fact-check the following claim: {query}

Verify:
1. Original source and context
2. Supporting evidence
3. Contradicting evidence
4. Expert opinions
5. Data and statistics
6. Historical accuracy
7. Consensus view

Provide confidence level and reasoning.
"""
        self.output_format = {
            'sections': [
                'Claim Summary',
                'Verdict',
                'Supporting Evidence',
                'Contradicting Evidence',
                'Context & Nuance',
                'Expert Analysis',
                'Conclusion'
            ]
        }


class AcademicResearchTemplate(ResearchTemplate):
    """Template for academic research papers"""
    
    def __init__(self):
        super().__init__(
            name="Academic Research",
            description="Structured academic research with citations",
            icon="🎓"
        )
        self.parameters = {
            'maxSources': 30,
            'includeYoutube': False,
            'requirePeerReviewed': True,
            'citationStyle': 'APA',
            'minCitations': 15,
            'includeMethodology': True
        }
        self.prompt_template = """
Conduct academic research on: {query}

Structure:
1. Abstract
2. Introduction and background
3. Literature review
4. Research questions/hypotheses
5. Methodology
6. Findings and analysis
7. Discussion
8. Limitations
9. Conclusions
10. References

Use formal academic tone and proper citations.
"""
        self.output_format = {
            'sections': [
                'Abstract',
                'Introduction',
                'Literature Review',
                'Research Questions',
                'Methodology',
                'Results',
                'Discussion',
                'Limitations',
                'Conclusion',
                'References'
            ]
        }


class BusinessIntelligenceTemplate(ResearchTemplate):
    """Template for business intelligence reports"""
    
    def __init__(self):
        super().__init__(
            name="Business Intelligence",
            description="Strategic business insights and recommendations",
            icon="💼"
        )
        self.parameters = {
            'maxSources': 15,
            'includeYoutube': False,
            'includeFinancials': True,
            'includeIndustryReports': True,
            'includeNews': True,
            'executiveSummary': True
        }
        self.prompt_template = """
Generate business intelligence report on: {query}

Analyze:
1. Industry landscape
2. Market dynamics
3. Key opportunities
4. Risk factors
5. Financial implications
6. Strategic recommendations
7. Implementation roadmap

Focus on actionable insights for decision-makers.
"""
        self.output_format = {
            'sections': [
                'Executive Summary',
                'Industry Analysis',
                'Market Dynamics',
                'Opportunities',
                'Risk Assessment',
                'Financial Impact',
                'Strategic Recommendations',
                'Action Plan'
            ]
        }


class TemplateManager:
    """Manages research templates"""
    
    def __init__(self):
        self.templates = {
            TemplateType.LITERATURE_REVIEW: LiteratureReviewTemplate(),
            TemplateType.MARKET_RESEARCH: MarketResearchTemplate(),
            TemplateType.COMPETITIVE_ANALYSIS: CompetitiveAnalysisTemplate(),
            TemplateType.TECHNICAL_DEEP_DIVE: TechnicalDeepDiveTemplate(),
            TemplateType.TREND_ANALYSIS: TrendAnalysisTemplate(),
            TemplateType.FACT_CHECK: FactCheckTemplate(),
            TemplateType.ACADEMIC_RESEARCH: AcademicResearchTemplate(),
            TemplateType.BUSINESS_INTELLIGENCE: BusinessIntelligenceTemplate()
        }
    
    def get_template(self, template_type: str) -> Optional[ResearchTemplate]:
        """Get template by type"""
        return self.templates.get(template_type)
    
    def list_templates(self) -> List[Dict]:
        """List all available templates"""
        return [
            {
                'id': key.value,
                'name': template.name,
                'description': template.description,
                'icon': template.icon
            }
            for key, template in self.templates.items()
        ]
    
    def apply_template(self, template_type: str, query: str) -> Dict:
        """Apply template to query"""
        template = self.get_template(template_type)
        if not template:
            return {'error': 'Template not found'}
        
        config = template.get_config()
        config['query'] = query
        config['prompt'] = template.prompt_template.format(query=query)
        
        return config


# Singleton instance
template_manager = TemplateManager()
