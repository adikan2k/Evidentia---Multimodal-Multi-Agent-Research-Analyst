"""
Visual Data Extraction System
Extracts and analyzes charts, graphs, tables, and images from sources
"""

from typing import Dict, List, Optional, Tuple
from enum import Enum
import re
import base64


class VisualType(str, Enum):
    """Types of visual content"""
    CHART = "chart"
    GRAPH = "graph"
    TABLE = "table"
    DIAGRAM = "diagram"
    INFOGRAPHIC = "infographic"
    IMAGE = "image"
    SCREENSHOT = "screenshot"


class VisualExtractor:
    """Extracts and analyzes visual data from sources"""
    
    def __init__(self):
        self.supported_formats = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp']
        self.table_patterns = [
            r'<table[^>]*>.*?</table>',
            r'\|[^\n]+\|',  # Markdown tables
        ]
    
    def extract_visuals(self, source: Dict) -> List[Dict]:
        """
        Extract all visual elements from a source
        
        Args:
            source: Source dictionary with HTML content
            
        Returns:
            List of extracted visual elements
        """
        visuals = []
        
        html = source.get('html', '')
        url = source.get('url', '')
        
        if not html:
            return visuals
        
        # Extract images
        images = self._extract_images(html, url)
        visuals.extend(images)
        
        # Extract tables
        tables = self._extract_tables(html)
        visuals.extend(tables)
        
        # Extract charts (from common chart libraries)
        charts = self._extract_charts(html)
        visuals.extend(charts)
        
        return visuals
    
    def _extract_images(self, html: str, base_url: str) -> List[Dict]:
        """Extract images from HTML"""
        images = []
        
        # Find all img tags
        img_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
        matches = re.findall(img_pattern, html, re.IGNORECASE)
        
        for img_url in matches:
            # Make absolute URL
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                from urllib.parse import urljoin
                img_url = urljoin(base_url, img_url)
            
            # Extract alt text
            alt_pattern = rf'<img[^>]+src=["\']{ re.escape(img_url)}["\'][^>]+alt=["\']([^"\']+)["\']'
            alt_match = re.search(alt_pattern, html, re.IGNORECASE)
            alt_text = alt_match.group(1) if alt_match else ''
            
            images.append({
                'type': VisualType.IMAGE,
                'url': img_url,
                'alt_text': alt_text,
                'description': alt_text,
                'format': self._get_image_format(img_url)
            })
        
        return images
    
    def _get_image_format(self, url: str) -> str:
        """Determine image format from URL"""
        for fmt in self.supported_formats:
            if url.lower().endswith(f'.{fmt}'):
                return fmt
        return 'unknown'
    
    def _extract_tables(self, html: str) -> List[Dict]:
        """Extract tables from HTML"""
        tables = []
        
        # Find all table tags
        table_pattern = r'<table[^>]*>(.*?)</table>'
        table_matches = re.findall(table_pattern, html, re.IGNORECASE | re.DOTALL)
        
        for i, table_html in enumerate(table_matches, 1):
            # Parse table structure
            table_data = self._parse_html_table(table_html)
            
            if table_data:
                tables.append({
                    'type': VisualType.TABLE,
                    'id': f'table_{i}',
                    'data': table_data,
                    'rows': len(table_data),
                    'columns': len(table_data[0]) if table_data else 0,
                    'html': f'<table>{table_html}</table>'
                })
        
        return tables
    
    def _parse_html_table(self, table_html: str) -> List[List[str]]:
        """Parse HTML table into 2D array"""
        rows = []
        
        # Find all rows
        row_pattern = r'<tr[^>]*>(.*?)</tr>'
        row_matches = re.findall(row_pattern, table_html, re.IGNORECASE | re.DOTALL)
        
        for row_html in row_matches:
            cells = []
            
            # Find all cells (th or td)
            cell_pattern = r'<t[hd][^>]*>(.*?)</t[hd]>'
            cell_matches = re.findall(cell_pattern, row_html, re.IGNORECASE | re.DOTALL)
            
            for cell_html in cell_matches:
                # Clean HTML tags
                cell_text = re.sub(r'<[^>]+>', '', cell_html).strip()
                cells.append(cell_text)
            
            if cells:
                rows.append(cells)
        
        return rows
    
    def _extract_charts(self, html: str) -> List[Dict]:
        """Extract charts from common chart libraries"""
        charts = []
        
        # Check for Chart.js
        if 'chart.js' in html.lower() or 'chartjs' in html.lower():
            chart_configs = self._extract_chartjs_config(html)
            charts.extend(chart_configs)
        
        # Check for D3.js
        if 'd3.js' in html.lower() or 'd3.min.js' in html.lower():
            charts.append({
                'type': VisualType.CHART,
                'library': 'D3.js',
                'description': 'Interactive D3.js visualization detected'
            })
        
        # Check for Plotly
        if 'plotly' in html.lower():
            charts.append({
                'type': VisualType.CHART,
                'library': 'Plotly',
                'description': 'Plotly chart detected'
            })
        
        return charts
    
    def _extract_chartjs_config(self, html: str) -> List[Dict]:
        """Extract Chart.js configurations"""
        charts = []
        
        # Look for Chart constructor calls
        chart_pattern = r'new Chart\([^,]+,\s*({[^}]+})\)'
        matches = re.findall(chart_pattern, html, re.DOTALL)
        
        for i, config in enumerate(matches, 1):
            charts.append({
                'type': VisualType.CHART,
                'id': f'chart_{i}',
                'library': 'Chart.js',
                'config': config,
                'description': f'Chart.js visualization #{i}'
            })
        
        return charts
    
    def analyze_table(self, table_data: List[List[str]]) -> Dict:
        """
        Analyze table structure and content
        
        Args:
            table_data: 2D array of table cells
            
        Returns:
            Table analysis
        """
        if not table_data:
            return {'error': 'Empty table'}
        
        rows = len(table_data)
        cols = len(table_data[0]) if table_data else 0
        
        # Detect header row
        has_header = self._detect_header(table_data)
        
        # Detect numeric columns
        numeric_cols = self._detect_numeric_columns(table_data, has_header)
        
        # Extract summary statistics
        stats = {}
        if numeric_cols:
            stats = self._calculate_table_stats(table_data, numeric_cols, has_header)
        
        return {
            'dimensions': {'rows': rows, 'columns': cols},
            'has_header': has_header,
            'header': table_data[0] if has_header else None,
            'numeric_columns': numeric_cols,
            'statistics': stats,
            'data_types': self._infer_column_types(table_data, has_header)
        }
    
    def _detect_header(self, table_data: List[List[str]]) -> bool:
        """Detect if first row is a header"""
        if not table_data or len(table_data) < 2:
            return False
        
        first_row = table_data[0]
        second_row = table_data[1]
        
        # Check if first row has text and second row has numbers
        first_has_text = any(not self._is_numeric(cell) for cell in first_row)
        second_has_numbers = any(self._is_numeric(cell) for cell in second_row)
        
        return first_has_text and second_has_numbers
    
    def _is_numeric(self, value: str) -> bool:
        """Check if value is numeric"""
        try:
            # Remove common formatting
            cleaned = value.replace(',', '').replace('$', '').replace('%', '').strip()
            float(cleaned)
            return True
        except:
            return False
    
    def _detect_numeric_columns(self, table_data: List[List[str]], has_header: bool) -> List[int]:
        """Detect which columns contain numeric data"""
        if not table_data:
            return []
        
        start_row = 1 if has_header else 0
        cols = len(table_data[0]) if table_data else 0
        numeric_cols = []
        
        for col_idx in range(cols):
            numeric_count = 0
            total_count = 0
            
            for row_idx in range(start_row, len(table_data)):
                if col_idx < len(table_data[row_idx]):
                    cell = table_data[row_idx][col_idx]
                    if cell.strip():
                        total_count += 1
                        if self._is_numeric(cell):
                            numeric_count += 1
            
            # If >70% of cells are numeric, consider it a numeric column
            if total_count > 0 and numeric_count / total_count > 0.7:
                numeric_cols.append(col_idx)
        
        return numeric_cols
    
    def _calculate_table_stats(self, table_data: List[List[str]], numeric_cols: List[int], has_header: bool) -> Dict:
        """Calculate statistics for numeric columns"""
        stats = {}
        start_row = 1 if has_header else 0
        
        for col_idx in numeric_cols:
            values = []
            
            for row_idx in range(start_row, len(table_data)):
                if col_idx < len(table_data[row_idx]):
                    cell = table_data[row_idx][col_idx]
                    if self._is_numeric(cell):
                        cleaned = cell.replace(',', '').replace('$', '').replace('%', '').strip()
                        try:
                            values.append(float(cleaned))
                        except:
                            pass
            
            if values:
                col_name = table_data[0][col_idx] if has_header and col_idx < len(table_data[0]) else f'Column {col_idx}'
                stats[col_name] = {
                    'min': min(values),
                    'max': max(values),
                    'mean': sum(values) / len(values),
                    'count': len(values)
                }
        
        return stats
    
    def _infer_column_types(self, table_data: List[List[str]], has_header: bool) -> List[str]:
        """Infer data type for each column"""
        if not table_data:
            return []
        
        start_row = 1 if has_header else 0
        cols = len(table_data[0]) if table_data else 0
        types = []
        
        for col_idx in range(cols):
            numeric_count = 0
            date_count = 0
            total_count = 0
            
            for row_idx in range(start_row, min(start_row + 10, len(table_data))):  # Sample first 10 rows
                if col_idx < len(table_data[row_idx]):
                    cell = table_data[row_idx][col_idx].strip()
                    if cell:
                        total_count += 1
                        if self._is_numeric(cell):
                            numeric_count += 1
                        elif self._is_date(cell):
                            date_count += 1
            
            if total_count == 0:
                types.append('empty')
            elif numeric_count / total_count > 0.7:
                types.append('numeric')
            elif date_count / total_count > 0.7:
                types.append('date')
            else:
                types.append('text')
        
        return types
    
    def _is_date(self, value: str) -> bool:
        """Check if value looks like a date"""
        date_patterns = [
            r'\d{1,2}/\d{1,2}/\d{2,4}',
            r'\d{4}-\d{2}-\d{2}',
            r'\d{1,2}-\w{3}-\d{2,4}',
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, value):
                return True
        return False
    
    def extract_chart_data(self, chart_config: str) -> Optional[Dict]:
        """
        Extract data from chart configuration
        
        Args:
            chart_config: Chart configuration string (JSON-like)
            
        Returns:
            Extracted chart data
        """
        try:
            import json
            # Try to parse as JSON
            config = json.loads(chart_config)
            
            return {
                'type': config.get('type', 'unknown'),
                'labels': config.get('data', {}).get('labels', []),
                'datasets': config.get('data', {}).get('datasets', []),
                'options': config.get('options', {})
            }
        except:
            return None
    
    def convert_table_to_csv(self, table_data: List[List[str]]) -> str:
        """Convert table data to CSV format"""
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        for row in table_data:
            writer.writerow(row)
        
        return output.getvalue()
    
    def generate_visual_summary(self, visuals: List[Dict]) -> Dict:
        """
        Generate summary of extracted visuals
        
        Args:
            visuals: List of extracted visual elements
            
        Returns:
            Summary statistics
        """
        summary = {
            'total_visuals': len(visuals),
            'by_type': {},
            'images': [],
            'tables': [],
            'charts': []
        }
        
        for visual in visuals:
            v_type = visual.get('type')
            summary['by_type'][v_type] = summary['by_type'].get(v_type, 0) + 1
            
            if v_type == VisualType.IMAGE:
                summary['images'].append(visual)
            elif v_type == VisualType.TABLE:
                summary['tables'].append(visual)
            elif v_type == VisualType.CHART:
                summary['charts'].append(visual)
        
        return summary


# Singleton instance
visual_extractor = VisualExtractor()
