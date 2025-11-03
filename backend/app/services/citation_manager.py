"""
Citation Management System
Supports multiple citation formats: APA, MLA, Chicago, Harvard, IEEE, Vancouver
"""

from typing import Dict, List, Optional
from datetime import datetime
import re
from urllib.parse import urlparse


class CitationManager:
    """Manages citations in multiple academic formats"""
    
    def __init__(self):
        self.supported_formats = ['APA', 'MLA', 'Chicago', 'Harvard', 'IEEE', 'Vancouver']
    
    def extract_metadata(self, source: Dict) -> Dict:
        """
        Extract citation metadata from source
        
        Args:
            source: Source dictionary with url, title, etc.
            
        Returns:
            Metadata dictionary with author, title, date, etc.
        """
        metadata = {
            'title': source.get('title', 'Untitled'),
            'url': source.get('url', ''),
            'access_date': datetime.now().strftime('%Y-%m-%d'),
            'publication_date': source.get('date', ''),
            'author': self._extract_author(source),
            'publisher': self._extract_publisher(source.get('url', '')),
            'type': source.get('type', 'website')
        }
        return metadata
    
    def _extract_author(self, source: Dict) -> str:
        """Extract or infer author from source"""
        if 'author' in source:
            return source['author']
        
        # Try to extract from metadata
        title = source.get('title', '')
        if ' - ' in title:
            parts = title.split(' - ')
            if len(parts) > 1:
                return parts[-1].strip()
        
        # Use publisher as fallback
        url = source.get('url', '')
        domain = urlparse(url).netloc
        return domain.replace('www.', '').split('.')[0].title()
    
    def _extract_publisher(self, url: str) -> str:
        """Extract publisher from URL"""
        domain = urlparse(url).netloc
        return domain.replace('www.', '').split('.')[0].title()
    
    def format_citation(self, metadata: Dict, style: str = 'APA') -> str:
        """
        Format citation in specified style
        
        Args:
            metadata: Citation metadata
            style: Citation style (APA, MLA, Chicago, Harvard, IEEE, Vancouver)
            
        Returns:
            Formatted citation string
        """
        style = style.upper()
        
        if style == 'APA':
            return self._format_apa(metadata)
        elif style == 'MLA':
            return self._format_mla(metadata)
        elif style == 'CHICAGO':
            return self._format_chicago(metadata)
        elif style == 'HARVARD':
            return self._format_harvard(metadata)
        elif style == 'IEEE':
            return self._format_ieee(metadata)
        elif style == 'VANCOUVER':
            return self._format_vancouver(metadata)
        else:
            return self._format_apa(metadata)  # Default to APA
    
    def _format_apa(self, meta: Dict) -> str:
        """APA 7th Edition format"""
        author = meta.get('author', 'Unknown')
        year = self._extract_year(meta.get('publication_date', ''))
        title = meta.get('title', 'Untitled')
        publisher = meta.get('publisher', '')
        url = meta.get('url', '')
        access_date = meta.get('access_date', '')
        
        citation = f"{author}. "
        if year:
            citation += f"({year}). "
        citation += f"{title}. "
        if publisher:
            citation += f"{publisher}. "
        citation += f"Retrieved {access_date}, from {url}"
        
        return citation
    
    def _format_mla(self, meta: Dict) -> str:
        """MLA 9th Edition format"""
        author = meta.get('author', 'Unknown')
        title = meta.get('title', 'Untitled')
        publisher = meta.get('publisher', '')
        date = meta.get('publication_date', 'n.d.')
        url = meta.get('url', '')
        access_date = meta.get('access_date', '')
        
        citation = f"{author}. \"{title}.\" "
        if publisher:
            citation += f"{publisher}, "
        citation += f"{date}. "
        citation += f"{url}. Accessed {access_date}."
        
        return citation
    
    def _format_chicago(self, meta: Dict) -> str:
        """Chicago 17th Edition format"""
        author = meta.get('author', 'Unknown')
        title = meta.get('title', 'Untitled')
        publisher = meta.get('publisher', '')
        date = meta.get('publication_date', 'n.d.')
        url = meta.get('url', '')
        access_date = meta.get('access_date', '')
        
        citation = f"{author}. \"{title}.\" "
        if publisher:
            citation += f"{publisher}. "
        citation += f"{date}. "
        citation += f"{url} (accessed {access_date})."
        
        return citation
    
    def _format_harvard(self, meta: Dict) -> str:
        """Harvard referencing format"""
        author = meta.get('author', 'Unknown')
        year = self._extract_year(meta.get('publication_date', ''))
        title = meta.get('title', 'Untitled')
        url = meta.get('url', '')
        access_date = meta.get('access_date', '')
        
        citation = f"{author} "
        if year:
            citation += f"{year}, "
        citation += f"'{title}', "
        citation += f"viewed {access_date}, <{url}>."
        
        return citation
    
    def _format_ieee(self, meta: Dict) -> str:
        """IEEE citation format"""
        author = meta.get('author', 'Unknown')
        title = meta.get('title', 'Untitled')
        publisher = meta.get('publisher', '')
        date = meta.get('publication_date', 'n.d.')
        url = meta.get('url', '')
        access_date = meta.get('access_date', '')
        
        citation = f"{author}, \"{title},\" "
        if publisher:
            citation += f"{publisher}, "
        citation += f"{date}. [Online]. Available: {url}. [Accessed: {access_date}]."
        
        return citation
    
    def _format_vancouver(self, meta: Dict) -> str:
        """Vancouver citation format"""
        author = meta.get('author', 'Unknown')
        title = meta.get('title', 'Untitled')
        publisher = meta.get('publisher', '')
        date = meta.get('publication_date', 'n.d.')
        url = meta.get('url', '')
        access_date = meta.get('access_date', '')
        
        citation = f"{author}. {title}. "
        if publisher:
            citation += f"{publisher}; "
        citation += f"{date}. Available from: {url} [cited {access_date}]."
        
        return citation
    
    def _extract_year(self, date_str: str) -> str:
        """Extract year from date string"""
        if not date_str:
            return ''
        
        # Try to find 4-digit year
        match = re.search(r'\b(19|20)\d{2}\b', date_str)
        if match:
            return match.group(0)
        
        return ''
    
    def generate_bibliography(self, sources: List[Dict], style: str = 'APA') -> str:
        """
        Generate complete bibliography from sources
        
        Args:
            sources: List of source dictionaries
            style: Citation style
            
        Returns:
            Formatted bibliography string
        """
        citations = []
        for i, source in enumerate(sources, 1):
            metadata = self.extract_metadata(source)
            citation = self.format_citation(metadata, style)
            citations.append(f"[{i}] {citation}")
        
        return '\n\n'.join(citations)
    
    def export_to_bibtex(self, sources: List[Dict]) -> str:
        """
        Export citations to BibTeX format
        
        Args:
            sources: List of source dictionaries
            
        Returns:
            BibTeX formatted string
        """
        bibtex_entries = []
        
        for i, source in enumerate(sources, 1):
            metadata = self.extract_metadata(source)
            author = metadata.get('author', 'Unknown').replace(' ', '')
            year = self._extract_year(metadata.get('publication_date', ''))
            
            entry = f"@misc{{ref{i},\n"
            entry += f"  author = {{{metadata.get('author', 'Unknown')}}},\n"
            entry += f"  title = {{{metadata.get('title', 'Untitled')}}},\n"
            if year:
                entry += f"  year = {{{year}}},\n"
            entry += f"  url = {{{metadata.get('url', '')}}},\n"
            entry += f"  note = {{Accessed: {metadata.get('access_date', '')}}}\n"
            entry += "}"
            
            bibtex_entries.append(entry)
        
        return '\n\n'.join(bibtex_entries)
    
    def export_to_ris(self, sources: List[Dict]) -> str:
        """
        Export citations to RIS format (for EndNote, Zotero, Mendeley)
        
        Args:
            sources: List of source dictionaries
            
        Returns:
            RIS formatted string
        """
        ris_entries = []
        
        for source in sources:
            metadata = self.extract_metadata(source)
            year = self._extract_year(metadata.get('publication_date', ''))
            
            entry = "TY  - ELEC\n"  # Electronic source
            entry += f"AU  - {metadata.get('author', 'Unknown')}\n"
            entry += f"TI  - {metadata.get('title', 'Untitled')}\n"
            if year:
                entry += f"PY  - {year}\n"
            entry += f"UR  - {metadata.get('url', '')}\n"
            entry += f"DA  - {metadata.get('access_date', '')}\n"
            entry += f"PB  - {metadata.get('publisher', '')}\n"
            entry += "ER  - \n"
            
            ris_entries.append(entry)
        
        return '\n'.join(ris_entries)


# Singleton instance
citation_manager = CitationManager()
