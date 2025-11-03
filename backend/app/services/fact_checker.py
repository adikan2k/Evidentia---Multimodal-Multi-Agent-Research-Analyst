"""
AI-Powered Fact Checking System
Verifies claims against multiple sources and provides confidence scores
"""

from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime
import re


class VerificationStatus(str, Enum):
    """Fact check verdict statuses"""
    TRUE = "true"
    MOSTLY_TRUE = "mostly_true"
    MIXED = "mixed"
    MOSTLY_FALSE = "mostly_false"
    FALSE = "false"
    UNVERIFIABLE = "unverifiable"
    NEEDS_CONTEXT = "needs_context"


class EvidenceType(str, Enum):
    """Types of evidence"""
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    NEUTRAL = "neutral"
    CONTEXT = "context"


class FactChecker:
    """AI-powered fact checking system"""
    
    def __init__(self):
        self.min_sources_required = 3
        self.confidence_threshold = 0.7
    
    def check_claim(self, claim: str, sources: List[Dict]) -> Dict:
        """
        Verify a claim against multiple sources
        
        Args:
            claim: Claim to verify
            sources: List of source documents
            
        Returns:
            Fact check result with verdict and evidence
        """
        # Extract evidence from sources
        evidence = self._extract_evidence(claim, sources)
        
        # Analyze evidence
        analysis = self._analyze_evidence(evidence)
        
        # Determine verdict
        verdict = self._determine_verdict(analysis)
        
        # Calculate confidence
        confidence = self._calculate_confidence(evidence, analysis)
        
        # Generate explanation
        explanation = self._generate_explanation(claim, verdict, evidence, analysis)
        
        return {
            'claim': claim,
            'verdict': verdict,
            'confidence': confidence,
            'evidence': evidence,
            'analysis': analysis,
            'explanation': explanation,
            'sources_checked': len(sources),
            'timestamp': datetime.now().isoformat()
        }
    
    def _extract_evidence(self, claim: str, sources: List[Dict]) -> List[Dict]:
        """Extract relevant evidence from sources"""
        evidence = []
        
        # Extract key terms from claim
        claim_terms = self._extract_key_terms(claim)
        
        for source in sources:
            text = source.get('text', '')
            if not text:
                continue
            
            # Find relevant passages
            relevance_score = self._calculate_relevance(claim_terms, text)
            
            if relevance_score > 0.3:  # Threshold for relevance
                # Determine evidence type
                evidence_type = self._classify_evidence(claim, text)
                
                # Extract specific quotes
                quotes = self._extract_quotes(claim, text)
                
                evidence.append({
                    'source': source.get('url', 'Unknown'),
                    'title': source.get('title', 'Untitled'),
                    'type': evidence_type,
                    'relevance': relevance_score,
                    'quotes': quotes,
                    'credibility': source.get('credibility_score', 0.5)
                })
        
        # Sort by relevance and credibility
        evidence.sort(key=lambda x: x['relevance'] * x['credibility'], reverse=True)
        
        return evidence
    
    def _extract_key_terms(self, text: str) -> List[str]:
        """Extract key terms from text"""
        # Remove common words
        stop_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 'in', 'with', 'to', 'for'}
        
        # Tokenize and filter
        words = re.findall(r'\b\w+\b', text.lower())
        key_terms = [w for w in words if w not in stop_words and len(w) > 3]
        
        return key_terms[:10]  # Top 10 terms
    
    def _calculate_relevance(self, claim_terms: List[str], text: str) -> float:
        """Calculate relevance score between claim and text"""
        text_lower = text.lower()
        matches = sum(1 for term in claim_terms if term in text_lower)
        
        if not claim_terms:
            return 0.0
        
        return matches / len(claim_terms)
    
    def _classify_evidence(self, claim: str, text: str) -> str:
        """Classify evidence as supporting, contradicting, or neutral"""
        claim_lower = claim.lower()
        text_lower = text.lower()
        
        # Check for explicit agreement/disagreement
        supporting_indicators = ['confirms', 'supports', 'proves', 'shows', 'demonstrates', 'validates']
        contradicting_indicators = ['contradicts', 'disproves', 'refutes', 'denies', 'disputes', 'challenges']
        
        support_count = sum(1 for ind in supporting_indicators if ind in text_lower)
        contradict_count = sum(1 for ind in contradicting_indicators if ind in text_lower)
        
        if support_count > contradict_count:
            return EvidenceType.SUPPORTING
        elif contradict_count > support_count:
            return EvidenceType.CONTRADICTING
        else:
            # Check for negation patterns
            if self._has_negation(claim_lower, text_lower):
                return EvidenceType.CONTRADICTING
            return EvidenceType.NEUTRAL
    
    def _has_negation(self, claim: str, text: str) -> bool:
        """Check if text negates the claim"""
        negation_words = ['not', 'no', 'never', 'false', 'incorrect', 'untrue', 'wrong']
        
        # Extract claim subject
        claim_words = claim.split()[:5]  # First few words
        
        for word in claim_words:
            if word in text:
                # Check if negation appears near the word
                word_index = text.find(word)
                context = text[max(0, word_index-50):word_index+50]
                
                if any(neg in context for neg in negation_words):
                    return True
        
        return False
    
    def _extract_quotes(self, claim: str, text: str, max_quotes: int = 3) -> List[str]:
        """Extract relevant quotes from text"""
        quotes = []
        
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        
        # Find sentences with high relevance
        claim_terms = self._extract_key_terms(claim)
        
        for sentence in sentences:
            if len(sentence.strip()) < 20:  # Skip very short sentences
                continue
            
            relevance = self._calculate_relevance(claim_terms, sentence)
            if relevance > 0.3:
                quotes.append({
                    'text': sentence.strip(),
                    'relevance': relevance
                })
        
        # Sort by relevance and return top quotes
        quotes.sort(key=lambda x: x['relevance'], reverse=True)
        return [q['text'] for q in quotes[:max_quotes]]
    
    def _analyze_evidence(self, evidence: List[Dict]) -> Dict:
        """Analyze collected evidence"""
        if not evidence:
            return {
                'supporting_count': 0,
                'contradicting_count': 0,
                'neutral_count': 0,
                'avg_credibility': 0.0,
                'consensus': None
            }
        
        supporting = [e for e in evidence if e['type'] == EvidenceType.SUPPORTING]
        contradicting = [e for e in evidence if e['type'] == EvidenceType.CONTRADICTING]
        neutral = [e for e in evidence if e['type'] == EvidenceType.NEUTRAL]
        
        # Calculate weighted scores
        support_score = sum(e['relevance'] * e['credibility'] for e in supporting)
        contradict_score = sum(e['relevance'] * e['credibility'] for e in contradicting)
        
        # Determine consensus
        if support_score > contradict_score * 2:
            consensus = 'strong_support'
        elif support_score > contradict_score:
            consensus = 'weak_support'
        elif contradict_score > support_score * 2:
            consensus = 'strong_contradiction'
        elif contradict_score > support_score:
            consensus = 'weak_contradiction'
        else:
            consensus = 'mixed'
        
        return {
            'supporting_count': len(supporting),
            'contradicting_count': len(contradicting),
            'neutral_count': len(neutral),
            'support_score': support_score,
            'contradict_score': contradict_score,
            'avg_credibility': sum(e['credibility'] for e in evidence) / len(evidence),
            'consensus': consensus
        }
    
    def _determine_verdict(self, analysis: Dict) -> str:
        """Determine fact check verdict based on analysis"""
        consensus = analysis.get('consensus')
        support_count = analysis.get('supporting_count', 0)
        contradict_count = analysis.get('contradicting_count', 0)
        
        # Need minimum sources
        total_sources = support_count + contradict_count
        if total_sources < self.min_sources_required:
            return VerificationStatus.UNVERIFIABLE
        
        # Determine verdict based on consensus
        if consensus == 'strong_support':
            return VerificationStatus.TRUE
        elif consensus == 'weak_support':
            return VerificationStatus.MOSTLY_TRUE
        elif consensus == 'strong_contradiction':
            return VerificationStatus.FALSE
        elif consensus == 'weak_contradiction':
            return VerificationStatus.MOSTLY_FALSE
        elif consensus == 'mixed':
            return VerificationStatus.MIXED
        else:
            return VerificationStatus.NEEDS_CONTEXT
    
    def _calculate_confidence(self, evidence: List[Dict], analysis: Dict) -> float:
        """Calculate confidence score for verdict"""
        if not evidence:
            return 0.0
        
        # Factors affecting confidence
        source_count = len(evidence)
        avg_credibility = analysis.get('avg_credibility', 0.5)
        consensus_strength = abs(analysis.get('support_score', 0) - analysis.get('contradict_score', 0))
        
        # Normalize factors
        source_factor = min(1.0, source_count / 10)  # Max at 10 sources
        credibility_factor = avg_credibility
        consensus_factor = min(1.0, consensus_strength / 5)  # Normalize
        
        # Weighted average
        confidence = (source_factor * 0.3 + credibility_factor * 0.4 + consensus_factor * 0.3)
        
        return round(confidence, 2)
    
    def _generate_explanation(self, claim: str, verdict: str, evidence: List[Dict], analysis: Dict) -> str:
        """Generate human-readable explanation"""
        explanation = f"Claim: '{claim}'\n\n"
        explanation += f"Verdict: {verdict.upper()}\n\n"
        
        # Summary
        support_count = analysis.get('supporting_count', 0)
        contradict_count = analysis.get('contradicting_count', 0)
        
        explanation += f"Analysis: We found {support_count} sources supporting this claim "
        explanation += f"and {contradict_count} sources contradicting it.\n\n"
        
        # Evidence summary
        if evidence:
            explanation += "Key Evidence:\n"
            for i, e in enumerate(evidence[:3], 1):
                explanation += f"{i}. {e['type'].upper()}: {e['title']}\n"
                if e['quotes']:
                    explanation += f"   Quote: \"{e['quotes'][0][:150]}...\"\n"
            explanation += "\n"
        
        # Conclusion
        if verdict == VerificationStatus.TRUE:
            explanation += "Conclusion: The claim is well-supported by multiple credible sources."
        elif verdict == VerificationStatus.MOSTLY_TRUE:
            explanation += "Conclusion: The claim is generally accurate but may lack some context."
        elif verdict == VerificationStatus.MIXED:
            explanation += "Conclusion: The evidence is mixed. The claim may be partially true or context-dependent."
        elif verdict == VerificationStatus.MOSTLY_FALSE:
            explanation += "Conclusion: The claim is largely contradicted by available evidence."
        elif verdict == VerificationStatus.FALSE:
            explanation += "Conclusion: The claim is clearly contradicted by multiple credible sources."
        elif verdict == VerificationStatus.UNVERIFIABLE:
            explanation += "Conclusion: Insufficient evidence to verify this claim."
        else:
            explanation += "Conclusion: This claim requires additional context to evaluate properly."
        
        return explanation
    
    def batch_check(self, claims: List[str], sources: List[Dict]) -> List[Dict]:
        """
        Check multiple claims
        
        Args:
            claims: List of claims to verify
            sources: List of source documents
            
        Returns:
            List of fact check results
        """
        results = []
        for claim in claims:
            result = self.check_claim(claim, sources)
            results.append(result)
        return results
    
    def cross_reference_citations(self, citations: List[Dict]) -> Dict:
        """
        Cross-reference citations to find contradictions
        
        Args:
            citations: List of citation dictionaries
            
        Returns:
            Cross-reference analysis
        """
        contradictions = []
        confirmations = []
        
        # Compare each citation with others
        for i, cite1 in enumerate(citations):
            for cite2 in citations[i+1:]:
                similarity = self._compare_claims(cite1.get('claim_span', ''), cite2.get('claim_span', ''))
                
                if similarity > 0.7:  # High similarity
                    # Check if they agree or contradict
                    if self._has_negation(cite1.get('claim_span', ''), cite2.get('claim_span', '')):
                        contradictions.append({
                            'citation1': cite1,
                            'citation2': cite2,
                            'similarity': similarity
                        })
                    else:
                        confirmations.append({
                            'citation1': cite1,
                            'citation2': cite2,
                            'similarity': similarity
                        })
        
        return {
            'contradictions': contradictions,
            'confirmations': confirmations,
            'consistency_score': len(confirmations) / max(1, len(confirmations) + len(contradictions))
        }
    
    def _compare_claims(self, claim1: str, claim2: str) -> float:
        """Calculate similarity between two claims"""
        terms1 = set(self._extract_key_terms(claim1))
        terms2 = set(self._extract_key_terms(claim2))
        
        if not terms1 or not terms2:
            return 0.0
        
        intersection = len(terms1 & terms2)
        union = len(terms1 | terms2)
        
        return intersection / union if union > 0 else 0.0


# Singleton instance
fact_checker = FactChecker()
