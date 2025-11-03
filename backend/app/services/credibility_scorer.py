"""
Source Credibility Scoring System
Evaluates source reliability based on multiple factors
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlparse
import re


class CredibilityScorer:
    """Evaluates source credibility and authority"""
    
    def __init__(self):
        # Trusted domain lists
        self.high_authority_domains = {
            # Academic
            'edu', 'ac.uk', 'edu.au', 'scholar.google.com', 'researchgate.net',
            'arxiv.org', 'pubmed.ncbi.nlm.nih.gov', 'nature.com', 'science.org',
            # Government
            'gov', 'gov.uk', 'europa.eu', 'who.int', 'un.org',
            # News (Tier 1)
            'reuters.com', 'apnews.com', 'bbc.com', 'npr.org', 'pbs.org',
            'theguardian.com', 'economist.com', 'ft.com', 'wsj.com', 'nytimes.com',
            # Tech/Industry
            'ieee.org', 'acm.org', 'techcrunch.com', 'arstechnica.com',
            # Medical
            'nih.gov', 'cdc.gov', 'mayoclinic.org', 'webmd.com'
        }
        
        self.medium_authority_domains = {
            'wikipedia.org', 'medium.com', 'forbes.com', 'bloomberg.com',
            'cnbc.com', 'cnn.com', 'washingtonpost.com', 'time.com',
            'scientificamerican.com', 'newscientist.com', 'wired.com'
        }
        
        self.low_credibility_indicators = [
            'clickbait', 'fake', 'hoax', 'conspiracy', 'unverified',
            'rumor', 'alleged', 'claims without evidence'
        ]
    
    def score_source(self, source: Dict) -> Dict:
        """
        Calculate comprehensive credibility score for a source
        
        Args:
            source: Source dictionary with url, title, text, metadata
            
        Returns:
            Credibility analysis with score and breakdown
        """
        url = source.get('url', '')
        title = source.get('title', '')
        text = source.get('text', '')
        date = source.get('date', '')
        
        # Calculate individual scores
        domain_score = self._score_domain(url)
        recency_score = self._score_recency(date)
        content_score = self._score_content(text)
        title_score = self._score_title(title)
        citation_score = self._score_citations(text)
        author_score = self._score_author(source)
        
        # Weighted average
        weights = {
            'domain': 0.30,
            'recency': 0.15,
            'content': 0.25,
            'title': 0.10,
            'citations': 0.15,
            'author': 0.05
        }
        
        total_score = (
            domain_score * weights['domain'] +
            recency_score * weights['recency'] +
            content_score * weights['content'] +
            title_score * weights['title'] +
            citation_score * weights['citations'] +
            author_score * weights['author']
        )
        
        # Determine credibility level
        if total_score >= 0.8:
            level = 'Very High'
        elif total_score >= 0.6:
            level = 'High'
        elif total_score >= 0.4:
            level = 'Medium'
        elif total_score >= 0.2:
            level = 'Low'
        else:
            level = 'Very Low'
        
        return {
            'overall_score': round(total_score, 2),
            'credibility_level': level,
            'breakdown': {
                'domain_authority': round(domain_score, 2),
                'recency': round(recency_score, 2),
                'content_quality': round(content_score, 2),
                'title_quality': round(title_score, 2),
                'citation_quality': round(citation_score, 2),
                'author_authority': round(author_score, 2)
            },
            'flags': self._identify_flags(source),
            'recommendations': self._generate_recommendations(total_score, source)
        }
    
    def _score_domain(self, url: str) -> float:
        """Score based on domain authority"""
        if not url:
            return 0.3
        
        domain = urlparse(url).netloc.lower()
        
        # Check high authority
        for auth_domain in self.high_authority_domains:
            if auth_domain in domain:
                return 1.0
        
        # Check medium authority
        for med_domain in self.medium_authority_domains:
            if med_domain in domain:
                return 0.7
        
        # Check TLD
        if domain.endswith('.edu') or domain.endswith('.gov'):
            return 0.9
        elif domain.endswith('.org'):
            return 0.6
        elif domain.endswith('.com'):
            return 0.5
        
        return 0.4  # Unknown domain
    
    def _score_recency(self, date_str: str) -> float:
        """Score based on publication recency"""
        if not date_str:
            return 0.5  # Unknown date
        
        try:
            # Try to parse date
            if isinstance(date_str, str):
                # Simple year extraction
                year_match = re.search(r'\b(20\d{2})\b', date_str)
                if year_match:
                    year = int(year_match.group(1))
                    current_year = datetime.now().year
                    age = current_year - year
                    
                    if age == 0:
                        return 1.0  # Current year
                    elif age <= 1:
                        return 0.9  # Last year
                    elif age <= 3:
                        return 0.7  # Last 3 years
                    elif age <= 5:
                        return 0.5  # Last 5 years
                    elif age <= 10:
                        return 0.3  # Last 10 years
                    else:
                        return 0.2  # Older
        except:
            pass
        
        return 0.5  # Default
    
    def _score_content(self, text: str) -> float:
        """Score based on content quality indicators"""
        if not text:
            return 0.3
        
        score = 0.5  # Base score
        
        # Length (longer generally better for research)
        word_count = len(text.split())
        if word_count > 1000:
            score += 0.2
        elif word_count > 500:
            score += 0.1
        elif word_count < 100:
            score -= 0.2
        
        # Academic indicators
        academic_terms = ['research', 'study', 'analysis', 'data', 'evidence', 
                         'methodology', 'findings', 'conclusion', 'peer-reviewed']
        academic_count = sum(1 for term in academic_terms if term in text.lower())
        score += min(0.2, academic_count * 0.03)
        
        # Check for low credibility indicators
        text_lower = text.lower()
        for indicator in self.low_credibility_indicators:
            if indicator in text_lower:
                score -= 0.1
        
        # Check for proper structure
        if '.' in text and text.count('.') > 5:  # Multiple sentences
            score += 0.05
        
        # Check for citations/references
        if 'reference' in text_lower or 'citation' in text_lower or 'source:' in text_lower:
            score += 0.1
        
        return max(0.0, min(1.0, score))
    
    def _score_title(self, title: str) -> float:
        """Score based on title quality"""
        if not title:
            return 0.3
        
        score = 0.5  # Base score
        
        # Check for clickbait indicators
        clickbait_words = ['shocking', 'unbelievable', 'you won\'t believe', 
                          'secret', 'trick', 'hack', 'amazing', 'incredible']
        title_lower = title.lower()
        
        for word in clickbait_words:
            if word in title_lower:
                score -= 0.2
        
        # Check for excessive punctuation
        if title.count('!') > 1 or title.count('?') > 1:
            score -= 0.1
        
        # Check for all caps
        if title.isupper() and len(title) > 10:
            score -= 0.2
        
        # Check for reasonable length
        word_count = len(title.split())
        if 5 <= word_count <= 20:
            score += 0.2
        
        return max(0.0, min(1.0, score))
    
    def _score_citations(self, text: str) -> float:
        """Score based on citation quality"""
        if not text:
            return 0.3
        
        score = 0.5  # Base score
        
        # Look for citation patterns
        citation_patterns = [
            r'\[\d+\]',  # [1], [2], etc.
            r'\(\d{4}\)',  # (2023), (2022), etc.
            r'et al\.',  # et al.
            r'doi:',  # DOI
            r'https?://[^\s]+',  # URLs
        ]
        
        citation_count = 0
        for pattern in citation_patterns:
            matches = re.findall(pattern, text)
            citation_count += len(matches)
        
        # Score based on citation density
        word_count = len(text.split())
        if word_count > 0:
            citation_density = citation_count / (word_count / 100)  # Per 100 words
            score += min(0.4, citation_density * 0.1)
        
        return max(0.0, min(1.0, score))
    
    def _score_author(self, source: Dict) -> float:
        """Score based on author information"""
        author = source.get('author', '')
        
        if not author or author.lower() in ['unknown', 'anonymous', 'admin']:
            return 0.3
        
        score = 0.5  # Base score
        
        # Check for credentials
        credentials = ['dr.', 'ph.d', 'professor', 'md', 'phd']
        author_lower = author.lower()
        
        for cred in credentials:
            if cred in author_lower:
                score += 0.3
                break
        
        # Check for full name (first and last)
        if len(author.split()) >= 2:
            score += 0.2
        
        return min(1.0, score)
    
    def _identify_flags(self, source: Dict) -> List[str]:
        """Identify potential credibility flags"""
        flags = []
        
        url = source.get('url', '')
        title = source.get('title', '')
        text = source.get('text', '')
        
        # Check for suspicious patterns
        if any(word in title.lower() for word in self.low_credibility_indicators):
            flags.append('Suspicious title content')
        
        if title.count('!') > 2:
            flags.append('Excessive punctuation in title')
        
        if not url:
            flags.append('No source URL provided')
        
        if not text or len(text.split()) < 100:
            flags.append('Insufficient content')
        
        domain = urlparse(url).netloc.lower()
        if not any(auth in domain for auth in self.high_authority_domains | self.medium_authority_domains):
            flags.append('Unknown or unverified source')
        
        return flags
    
    def _generate_recommendations(self, score: float, source: Dict) -> List[str]:
        """Generate recommendations based on credibility score"""
        recommendations = []
        
        if score < 0.5:
            recommendations.append('Verify information with additional high-authority sources')
            recommendations.append('Check for author credentials and expertise')
            recommendations.append('Look for peer-reviewed or official sources')
        
        if score < 0.7:
            recommendations.append('Cross-reference key claims with other sources')
            recommendations.append('Check publication date for recency')
        
        if not source.get('date'):
            recommendations.append('Verify publication date')
        
        if not source.get('author'):
            recommendations.append('Identify the author and their credentials')
        
        return recommendations
    
    def batch_score(self, sources: List[Dict]) -> List[Dict]:
        """
        Score multiple sources
        
        Args:
            sources: List of source dictionaries
            
        Returns:
            List of sources with credibility scores added
        """
        scored_sources = []
        
        for source in sources:
            credibility = self.score_source(source)
            source_with_score = source.copy()
            source_with_score['credibility'] = credibility
            source_with_score['credibility_score'] = credibility['overall_score']
            scored_sources.append(source_with_score)
        
        # Sort by credibility score
        scored_sources.sort(key=lambda x: x['credibility_score'], reverse=True)
        
        return scored_sources
    
    def filter_by_credibility(self, sources: List[Dict], min_score: float = 0.5) -> List[Dict]:
        """
        Filter sources by minimum credibility score
        
        Args:
            sources: List of source dictionaries
            min_score: Minimum credibility score (0.0 to 1.0)
            
        Returns:
            Filtered list of sources
        """
        scored_sources = self.batch_score(sources)
        return [s for s in scored_sources if s['credibility_score'] >= min_score]
    
    def get_credibility_report(self, sources: List[Dict]) -> Dict:
        """
        Generate comprehensive credibility report
        
        Args:
            sources: List of source dictionaries
            
        Returns:
            Credibility report with statistics
        """
        scored_sources = self.batch_score(sources)
        
        if not scored_sources:
            return {
                'total_sources': 0,
                'average_score': 0.0,
                'distribution': {},
                'high_credibility_count': 0,
                'low_credibility_count': 0
            }
        
        scores = [s['credibility_score'] for s in scored_sources]
        
        return {
            'total_sources': len(scored_sources),
            'average_score': round(sum(scores) / len(scores), 2),
            'highest_score': max(scores),
            'lowest_score': min(scores),
            'distribution': {
                'very_high': len([s for s in scores if s >= 0.8]),
                'high': len([s for s in scores if 0.6 <= s < 0.8]),
                'medium': len([s for s in scores if 0.4 <= s < 0.6]),
                'low': len([s for s in scores if 0.2 <= s < 0.4]),
                'very_low': len([s for s in scores if s < 0.2])
            },
            'high_credibility_sources': [s for s in scored_sources if s['credibility_score'] >= 0.7],
            'flagged_sources': [s for s in scored_sources if s['credibility'].get('flags')]
        }


# Singleton instance
credibility_scorer = CredibilityScorer()
