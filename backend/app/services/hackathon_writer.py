"""
HACKATHON-GRADE Report Writer
Zero Generic Content - Everything Query-Specific
"""

from typing import List, Dict, Any, Tuple
import re
from datetime import datetime
from collections import Counter


class HackathonReportWriter:
    """
    Ultra-specific report generator for global hackathon
    RULE: Zero generic phrases, everything evidence-based
    """
    
    def __init__(self):
        self.min_passage_length = 100
    
    def generate_report(self, query: str, passages: List[Dict[str, Any]], 
                       intelligence_metrics: Dict = None) -> Dict[str, Any]:
        """Generate 100% query-specific, evidence-based report"""
        
        if not passages or len(passages) == 0:
            return {
                "html": f"<h1>{query}</h1><p>No sources found. Unable to generate report.</p>",
                "citations": [],
                "sources": []
            }
        
        # Analyze query and content
        query_analysis = self._analyze_query_deep(query)
        content = self._extract_all_evidence(passages, query)
        
        # Build ultra-specific report
        html_parts = []
        citations = []
        
        # Each section must be query-specific
        html_parts.extend(self._generate_specific_header(query, passages, intelligence_metrics, content))
        
        summary_html, summary_cites = self._generate_evidence_summary(query, content, query_analysis, passages)
        html_parts.append(summary_html)
        citations.extend(summary_cites)
        
        # Main findings with real evidence
        findings_html, findings_cites = self._generate_evidence_findings(query, content, passages)
        html_parts.append(findings_html)
        citations.extend(findings_cites)
        
        # Comparative if applicable
        if query_analysis['is_comparative']:
            comp_html = self._generate_real_comparison(query, passages)
            html_parts.append(comp_html)
        
        # Data section if numbers found
        if content['statistics']:
            html_parts.append(self._generate_data_section(content, query))
        
        # Methodology - specific to THIS research
        html_parts.append(self._generate_specific_methodology(query, passages, intelligence_metrics, query_analysis))
        
        # Limitations - specific to THIS research
        html_parts.append(self._generate_specific_limitations(query, passages, query_analysis, content))
        
        # Future research - based on actual gaps
        html_parts.append(self._generate_identified_gaps(query, content, passages))
        
        # Conclusion - pure evidence
        html_parts.append(self._generate_evidence_conclusion(query, content, passages, query_analysis))
        
        # References
        sources = self._extract_sources(passages)
        html_parts.append(self._generate_references(sources))
        
        return {
            "html": "\n".join(html_parts),
            "citations": citations,
            "sources": sources,
            "metadata": {"query_analysis": query_analysis, "themes": content['themes']}
        }
    
    def _analyze_query_deep(self, query: str) -> Dict:
        """Deep query analysis for maximum specificity"""
        q_lower = query.lower()
        
        # Extract all meaningful terms
        words = re.findall(r'\b[a-zA-Z]{3,}\b', query)
        key_terms = [w for w in words if w.lower() not in {'the', 'and', 'for', 'how', 'what', 'why'}]
        
        return {
            'is_comparative': any(w in q_lower for w in [' vs ', ' versus ', 'compare', 'difference between']),
            'is_causal': any(w in q_lower for w in ['why', 'cause', 'reason', 'because']),
            'is_how_to': q_lower.startswith('how') or 'how to' in q_lower,
            'is_trend': any(w in q_lower for w in ['trend', '2024', '2025', 'future', 'upcoming']),
            'is_evaluation': any(w in q_lower for w in ['best', 'top', 'should', 'better']),
            'key_terms': key_terms,
            'domain': self._detect_domain(q_lower),
            'entities': [w for w in words if w[0].isupper()]
        }
    
    def _detect_domain(self, query_lower: str) -> str:
        """Detect specific domain"""
        domains = {
            'ai/ml': ['ai', 'machine learning', 'neural', 'gpt', 'model', 'llm', 'deep learning'],
            'programming': ['python', 'javascript', 'code', 'programming', 'developer', 'api'],
            'web': ['web', 'frontend', 'backend', 'react', 'framework', 'css'],
            'data': ['data', 'database', 'sql', 'analytics', 'visualization'],
            'healthcare': ['health', 'medical', 'disease', 'treatment', 'patient'],
            'business': ['business', 'market', 'revenue', 'strategy', 'company']
        }
        
        for domain, keywords in domains.items():
            if any(kw in query_lower for kw in keywords):
                return domain
        return 'general'
    
    def _extract_all_evidence(self, passages: List[Dict], query: str) -> Dict:
        """Extract ALL evidence from sources"""
        all_text = " ".join([p.get('text', '') for p in passages])
        query_words = set(query.lower().split())
        
        # Extract themes (query-relevant only)
        words = re.findall(r'\b[a-z]{4,}\b', all_text.lower())
        word_freq = Counter(words)
        stop_words = {'that', 'this', 'with', 'from', 'have', 'been', 'were', 'their', 'also'}
        
        # Only themes that appear WITH query terms
        relevant_themes = []
        for word, count in word_freq.most_common(20):
            if word in stop_words or count < 2:
                continue
            # Check if appears near query terms
            for sent in re.split(r'[.!?]+', all_text):
                if word in sent.lower() and any(qw in sent.lower() for qw in query_words):
                    relevant_themes.append(word)
                    break
        
        return {
            'primary': passages[:3],
            'supporting': passages[3:8],
            'themes': relevant_themes[:5],
            'statistics': self._extract_stats_with_context(passages, query),
            'key_sentences': self._extract_key_sentences(passages, query)
        }
    
    def _extract_stats_with_context(self, passages: List[Dict], query: str) -> List[Dict]:
        """Extract statistics with full context"""
        stats = []
        query_words = set(query.lower().split())
        
        for passage in passages[:8]:
            text = passage.get('text', '')
            sentences = re.split(r'[.!?]+', text)
            
            for sentence in sentences:
                # Find numbers
                numbers = re.findall(r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*(billion|million|thousand|percent|%|times)', sentence, re.I)
                
                if not numbers:
                    continue
                
                # Must be relevant to query
                sentence_words = set(sentence.lower().split())
                overlap = len(query_words & sentence_words)
                
                if overlap >= 1:  # At least one query term
                    for num, unit in numbers[:1]:
                        # Extract what it measures
                        label = self._extract_measurement(sentence, num, unit, query)
                        
                        stats.append({
                            'value': f"{num} {unit}",
                            'label': label,
                            'context': sentence.strip()[:150],
                            'source': passage.get('title', 'Source')
                        })
                        
                        if len(stats) >= 6:
                            return stats
        
        return stats
    
    def _extract_measurement(self, sentence: str, num: str, unit: str, query: str) -> str:
        """Extract what the number actually measures"""
        # Look for noun phrases around the number
        parts = sentence.lower().split(f"{num} {unit}")
        
        # Common patterns
        if len(parts) >= 2:
            after_text = parts[1].strip().split()[:5]
            if len(after_text) >= 2:
                return ' '.join(after_text).strip('.,;:').title()
            
            before_text = parts[0].strip().split()[-5:]
            if len(before_text) >= 2:
                return ' '.join(before_text).strip('.,;:').title()
        
        # Extract nouns from sentence
        words = re.findall(r'\b[a-z]{4,}\b', sentence.lower())
        query_words = query.lower().split()
        
        # Find words that appear in query
        for word in words:
            if word in query_words:
                return word.title()
        
        return "Metric"
    
    def _extract_key_sentences(self, passages: List[Dict], query: str) -> List[str]:
        """Extract most relevant sentences"""
        query_words = set(query.lower().split())
        key_sentences = []
        
        for passage in passages[:5]:
            text = passage.get('text', '')
            sentences = re.split(r'[.!?]+', text)
            
            for sentence in sentences:
                if 50 < len(sentence) < 250:
                    sent_words = set(sentence.lower().split())
                    overlap = len(query_words & sent_words)
                    
                    if overlap >= 2:  # At least 2 query terms
                        key_sentences.append(sentence.strip())
                        
                        if len(key_sentences) >= 5:
                            return key_sentences
        
        return key_sentences
    
    def _generate_specific_header(self, query: str, passages: List[Dict], 
                                   metrics: Dict, content: Dict) -> List[str]:
        """Header with specific research scope"""
        now = datetime.now()
        quality = metrics.get('content_quality_score', 0) if metrics else 0
        
        header = [
            f"<h1>Research Analysis: {query}</h1>",
            "<div class='report-header'>",
            f"<p class='report-meta'><strong>Research Date:</strong> {now.strftime('%B %d, %Y')}</p>",
            f"<p class='report-meta'><strong>Sources:</strong> {len(passages)} sources analyzed</p>",
        ]
        
        if quality > 0:
            header.append(f"<p class='report-meta'><strong>Quality Score:</strong> {quality:.1f}/100</p>")
        
        if content['themes']:
            header.append(f"<p class='report-meta'><strong>Key Topics:</strong> {', '.join(content['themes'][:4])}</p>")
        
        header.append("</div>")
        return header
    
    def _generate_evidence_summary(self, query: str, content: Dict, 
                                    analysis: Dict, passages: List[Dict]) -> Tuple[str, List]:
        """Summary built ONLY from actual evidence"""
        html_parts = ["<h2>Research Summary</h2>"]
        citations = []
        
        # Opening with specific scope
        key_terms = ', '.join(analysis['key_terms'][:4])
        opening = f"<p>This research examines <strong>{query}</strong>, focusing on {key_terms}. "
        opening += f"Analysis of {len(passages)} sources "
        
        if content['statistics']:
            opening += f"reveals {len(content['statistics'])} quantifiable metrics "
        
        if content['themes']:
            opening += f"and identifies {len(content['themes'])} core themes: {', '.join(content['themes'][:3])}. "
        
        opening += "</p>"
        html_parts.append(opening)
        
        # Evidence-based insights ONLY
        if content['key_sentences']:
            html_parts.append("<p><strong>Core Evidence:</strong></p>")
            html_parts.append("<ul class='executive-insights'>")
            
            for i, sentence in enumerate(content['key_sentences'][:4], 1):
                html_parts.append(f"<li>{sentence}</li>")
                citations.append({
                    "claim_span": f"Evidence {i}",
                    "quote_span": sentence[:150],
                    "url": passages[min(i-1, len(passages)-1)].get('url', '')
                })
            
            html_parts.append("</ul>")
        
        return "\n".join(html_parts), citations
    
    def _generate_evidence_findings(self, query: str, content: Dict, 
                                     passages: List[Dict]) -> Tuple[str, List]:
        """Findings - pure evidence extraction"""
        html_parts = ["<h2>Research Findings</h2>"]
        citations = []
        
        # Primary evidence
        html_parts.append(f"<h3>Primary Evidence ({len(content['primary'])} sources)</h3>")
        
        for i, passage in enumerate(content['primary'], 1):
            text = passage.get('text', '')
            title = passage.get('title', f'Source {i}')
            url = passage.get('url', '')
            
            # Extract most relevant excerpt
            excerpt = self._extract_relevant_text(text, query, max_length=400)
            
            html_parts.append(f"""
            <div class='finding-card-primary'>
                <h4>Source {i}: {title}</h4>
                <p>{excerpt}</p>
                <p class='source-link'><a href='{url}' target='_blank'>View Source →</a></p>
            </div>
            """)
            
            citations.append({"claim_span": f"Source {i}", "quote_span": excerpt[:200], "url": url})
        
        # Supporting evidence
        if content['supporting']:
            html_parts.append(f"<h3>Supporting Evidence ({len(content['supporting'])} sources)</h3>")
            
            for i, passage in enumerate(content['supporting'][:3], len(content['primary']) + 1):
                text = passage.get('text', '')
                title = passage.get('title', f'Source {i}')
                url = passage.get('url', '')
                
                excerpt = self._extract_relevant_text(text, query, max_length=300)
                
                html_parts.append(f"""
                <div class='finding-card'>
                    <h4>{title}</h4>
                    <p>{excerpt}</p>
                </div>
                """)
        
        return "\n".join(html_parts), citations
    
    def _extract_relevant_text(self, text: str, query: str, max_length: int = 400) -> str:
        """Extract most query-relevant text"""
        query_words = set(query.lower().split())
        sentences = re.split(r'[.!?]+', text)
        
        # Score sentences
        scored = []
        for sent in sentences:
            if len(sent) < 30:
                continue
            
            sent_words = set(sent.lower().split())
            overlap = len(query_words & sent_words)
            
            if overlap > 0:
                scored.append((overlap, sent.strip()))
        
        scored.sort(reverse=True, key=lambda x: x[0])
        
        # Combine top sentences
        result = ""
        for score, sent in scored[:3]:
            if len(result) + len(sent) < max_length:
                result += sent + ". "
        
        return result.strip() if result else text[:max_length] + "..."
    
    def _generate_real_comparison(self, query: str, passages: List[Dict]) -> str:
        """Real comparison with actual data"""
        # Extract subjects
        subjects = []
        if ' vs ' in query.lower():
            subjects = [s.strip() for s in query.lower().split(' vs ')[:2]]
        elif 'compare' in query.lower():
            words = query.split()
            subjects = [w for w in words if len(w) > 3 and w[0].isupper()][:2]
        
        if len(subjects) < 2:
            return ""
        
        html_parts = [f"<h2>Comparative Analysis: {subjects[0].title()} vs {subjects[1].title()}</h2>"]
        
        # Extract evidence for each subject
        data = {subjects[0]: [], subjects[1]: []}
        
        for passage in passages[:8]:
            text = passage.get('text', '')
            sentences = re.split(r'[.!?]+', text)
            
            for sent in sentences:
                sent_lower = sent.lower()
                if subjects[0] in sent_lower and len(sent) > 40:
                    data[subjects[0]].append(sent.strip())
                if subjects[1] in sent_lower and len(sent) > 40:
                    data[subjects[1]].append(sent.strip())
        
        # Build comparison
        html_parts.append(f"<h3>{subjects[0].title()}</h3>")
        html_parts.append("<ul>")
        for sent in data[subjects[0]][:3]:
            html_parts.append(f"<li>{sent}</li>")
        html_parts.append("</ul>")
        
        html_parts.append(f"<h3>{subjects[1].title()}</h3>")
        html_parts.append("<ul>")
        for sent in data[subjects[1]][:3]:
            html_parts.append(f"<li>{sent}</li>")
        html_parts.append("</ul>")
        
        return "\n".join(html_parts)
    
    def _generate_data_section(self, content: Dict, query: str) -> str:
        """Data section with context"""
        stats = content['statistics']
        
        html_parts = ["<h2>Quantitative Data</h2>"]
        html_parts.append(f"<p>The following {len(stats)} metrics directly relate to {query}:</p>")
        html_parts.append("<div class='statistics-grid'>")
        
        for stat in stats:
            html_parts.append(f"""
            <div class='stat-card'>
                <div class='stat-value'>{stat['value']}</div>
                <div class='stat-label'>{stat['label']}</div>
                <div class='stat-source'>{stat['source']}</div>
            </div>
            """)
        
        html_parts.append("</div>")
        return "\n".join(html_parts)
    
    def _generate_specific_methodology(self, query: str, passages: List[Dict], 
                                        metrics: Dict, analysis: Dict) -> str:
        """Methodology specific to THIS research"""
        html_parts = ["<h2>Research Methodology</h2>"]
        
        html_parts.append(f"<p>To investigate '{query}', this research employed the following approach:</p>")
        html_parts.append("<ul>")
        html_parts.append(f"<li><strong>Query Analysis:</strong> Identified key terms ({', '.join(analysis['key_terms'][:4])}) and research domain ({analysis['domain']})</li>")
        html_parts.append(f"<li><strong>Source Selection:</strong> Analyzed {len(passages)} sources selected for relevance to the specific query terms</li>")
        
        if metrics:
            quality = metrics.get('content_quality_score', 0)
            html_parts.append(f"<li><strong>Quality Filter:</strong> Sources averaged {quality:.1f}/100 quality score</li>")
        
        html_parts.append(f"<li><strong>Evidence Extraction:</strong> Identified sentences containing 2+ query terms for maximum relevance</li>")
        html_parts.append(f"<li><strong>Theme Analysis:</strong> Extracted recurring concepts that co-occur with query terms</li>")
        html_parts.append("</ul>")
        
        return "\n".join(html_parts)
    
    def _generate_specific_limitations(self, query: str, passages: List[Dict], 
                                        analysis: Dict, content: Dict) -> str:
        """Limitations specific to THIS research"""
        html_parts = ["<h2>Research Limitations</h2>"]
        html_parts.append(f"<p>The following limitations apply specifically to this investigation of '{query}':</p>")
        html_parts.append("<ul>")
        
        # Actual limitations based on the research
        html_parts.append(f"<li><strong>Source Count:</strong> Analysis limited to {len(passages)} sources; additional sources may exist</li>")
        
        if len(content['statistics']) == 0:
            html_parts.append(f"<li><strong>Quantitative Data:</strong> No statistical metrics found in analyzed sources for this specific query</li>")
        
        if analysis['domain'] != 'general':
            html_parts.append(f"<li><strong>Domain Scope:</strong> Research focused on {analysis['domain']} domain; cross-domain insights may be limited</li>")
        
        html_parts.append(f"<li><strong>Temporal Scope:</strong> Sources reflect information available at time of research; rapidly evolving topics may have newer developments</li>")
        
        if len(content['themes']) < 3:
            html_parts.append(f"<li><strong>Theme Diversity:</strong> Only {len(content['themes'])} distinct themes identified; topic may have additional dimensions</li>")
        
        html_parts.append("</ul>")
        return "\n".join(html_parts)
    
    def _generate_identified_gaps(self, query: str, content: Dict, passages: List[Dict]) -> str:
        """Future research based on actual gaps found"""
        html_parts = ["<h2>Research Gaps & Future Directions</h2>"]
        html_parts.append(f"<p>Based on the analysis of '{query}', the following specific gaps were identified:</p>")
        html_parts.append("<ul>")
        
        # Identify actual gaps
        if len(content['statistics']) < 2:
            html_parts.append(f"<li><strong>Quantitative Analysis:</strong> Limited statistical data found; future research should include controlled studies with measurable metrics</li>")
        
        if len(passages) < 10:
            html_parts.append(f"<li><strong>Source Depth:</strong> Expand to {len(passages) + 10}+ sources to capture broader perspectives on {query}</li>")
        
        # Query-type specific gaps
        if 'compare' in query.lower():
            html_parts.append(f"<li><strong>Systematic Comparison:</strong> Conduct controlled comparative study with standardized evaluation criteria</li>")
        
        if 'trend' in query.lower() or '2024' in query or '2025' in query:
            html_parts.append(f"<li><strong>Longitudinal Data:</strong> Track developments over extended time periods for trend validation</li>")
        
        html_parts.append(f"<li><strong>Domain Expertise:</strong> Engage specialists in {content['themes'][0] if content['themes'] else 'relevant areas'} for deeper technical analysis</li>")
        
        html_parts.append("</ul>")
        return "\n".join(html_parts)
    
    def _generate_evidence_conclusion(self, query: str, content: Dict, 
                                       passages: List[Dict], analysis: Dict) -> str:
        """Conclusion built entirely from evidence"""
        html_parts = ["<h2>Conclusion</h2>"]
        
        # Summary with specific numbers
        opening = f"<p>This investigation of '{query}' analyzed {len(passages)} sources, "
        
        if content['statistics']:
            opening += f"identified {len(content['statistics'])} quantifiable metrics, "
        
        if content['themes']:
            opening += f"and extracted {len(content['themes'])} core themes ({', '.join(content['themes'][:3])}). "
        
        opening += "</p>"
        html_parts.append(opening)
        
        # Evidence-based key takeaway
        html_parts.append("<div class='key-takeaway'>")
        html_parts.append(f"<h3>🎯 Evidence-Based Conclusion</h3>")
        
        if content['key_sentences']:
            takeaway = f"<p>The research evidence on '{query}' converges on specific findings: "
            takeaway += content['key_sentences'][0] + " "
            
            if len(content['key_sentences']) > 1:
                takeaway += content['key_sentences'][1] + " "
            
            takeaway += f"These findings, drawn from {len(passages)} independent sources, "
            takeaway += f"provide a {('high' if len(passages) >= 5 else 'moderate')}-confidence foundation for understanding {query}.</p>"
        else:
            takeaway = f"<p>Based on {len(passages)} sources, the evidence about '{query}' indicates need for deeper investigation with more comprehensive data.</p>"
        
        html_parts.append(takeaway)
        html_parts.append("</div>")
        
        # Specific confidence
        confidence = f"<p><strong>Confidence Assessment:</strong> "
        confidence += f"{'High' if len(passages) >= 5 else 'Moderate'} ({len(passages)} sources analyzed). "
        
        if content['statistics']:
            confidence += f"{len(content['statistics'])} quantitative metrics provide measurable validation. "
        
        if content['themes'] and len(content['themes']) >= 3:
            confidence += f"{len(content['themes'])} recurring themes indicate conceptual convergence across sources. "
        
        confidence += "</p>"
        html_parts.append(confidence)
        
        return "\n".join(html_parts)
    
    def _extract_sources(self, passages: List[Dict]) -> List[Dict]:
        """Extract sources"""
        sources = []
        seen = set()
        
        for p in passages:
            url = p.get('url', '')
            if url and url not in seen:
                sources.append({'title': p.get('title', 'Source'), 'url': url})
                seen.add(url)
        
        return sources
    
    def _generate_references(self, sources: List[Dict]) -> str:
        """Generate references"""
        html_parts = ["<h2>References</h2>", "<ol class='references'>"]
        
        for i, source in enumerate(sources, 1):
            html_parts.append(f"<li>{source['title']}. <a href='{source['url']}' target='_blank'>{source['url']}</a></li>")
        
        html_parts.append("</ol>")
        return "\n".join(html_parts)


# Singleton
hackathon_writer = HackathonReportWriter()
