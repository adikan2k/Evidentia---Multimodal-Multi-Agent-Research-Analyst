"""
Multi-Language Translation Service
Supports automatic language detection and translation using multiple providers
"""

from typing import Dict, List, Optional, Tuple
from enum import Enum
import re


class Language(str, Enum):
    """Supported languages"""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    CHINESE = "zh"
    JAPANESE = "ja"
    KOREAN = "ko"
    PORTUGUESE = "pt"
    RUSSIAN = "ru"
    ARABIC = "ar"
    HINDI = "hi"
    ITALIAN = "it"
    DUTCH = "nl"
    TURKISH = "tr"
    POLISH = "pl"


class TranslationProvider(str, Enum):
    """Translation service providers"""
    GOOGLE = "google"
    DEEPL = "deepl"
    AZURE = "azure"
    LOCAL = "local"  # For offline translation


class TranslationService:
    """Multi-language translation service"""
    
    def __init__(self, provider: str = "google"):
        self.provider = provider
        self.supported_languages = [lang.value for lang in Language]
        self.language_names = {
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "zh": "Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "pt": "Portuguese",
            "ru": "Russian",
            "ar": "Arabic",
            "hi": "Hindi",
            "it": "Italian",
            "nl": "Dutch",
            "tr": "Turkish",
            "pl": "Polish"
        }
    
    def detect_language(self, text: str) -> Tuple[str, float]:
        """
        Detect language of text
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (language_code, confidence)
        """
        # Simple heuristic-based detection
        # In production, use proper language detection library
        
        # Check for common patterns
        if re.search(r'[\u4e00-\u9fff]', text):
            return ('zh', 0.95)
        elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
            return ('ja', 0.95)
        elif re.search(r'[\uac00-\ud7af]', text):
            return ('ko', 0.95)
        elif re.search(r'[\u0600-\u06ff]', text):
            return ('ar', 0.95)
        elif re.search(r'[\u0400-\u04ff]', text):
            return ('ru', 0.90)
        
        # Check for common English words
        english_words = ['the', 'is', 'and', 'to', 'of', 'in', 'for', 'on', 'with']
        text_lower = text.lower()
        english_count = sum(1 for word in english_words if word in text_lower)
        
        if english_count >= 3:
            return ('en', 0.85)
        
        # Default to English with low confidence
        return ('en', 0.50)
    
    async def translate(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict:
        """
        Translate text to target language
        
        Args:
            text: Text to translate
            target_lang: Target language code
            source_lang: Source language code (auto-detect if None)
            
        Returns:
            Translation result with metadata
        """
        if not source_lang:
            source_lang, confidence = self.detect_language(text)
        else:
            confidence = 1.0
        
        # Skip translation if already in target language
        if source_lang == target_lang:
            return {
                'original_text': text,
                'translated_text': text,
                'source_language': source_lang,
                'target_language': target_lang,
                'confidence': confidence,
                'provider': self.provider
            }
        
        # Perform translation based on provider
        if self.provider == "google":
            translated = await self._translate_google(text, source_lang, target_lang)
        elif self.provider == "deepl":
            translated = await self._translate_deepl(text, source_lang, target_lang)
        elif self.provider == "azure":
            translated = await self._translate_azure(text, source_lang, target_lang)
        else:
            translated = await self._translate_local(text, source_lang, target_lang)
        
        return {
            'original_text': text,
            'translated_text': translated,
            'source_language': source_lang,
            'target_language': target_lang,
            'confidence': confidence,
            'provider': self.provider
        }
    
    async def _translate_google(self, text: str, source: str, target: str) -> str:
        """Translate using Google Translate API"""
        try:
            from googletrans import Translator
            translator = Translator()
            result = translator.translate(text, src=source, dest=target)
            return result.text
        except Exception as e:
            print(f"Google Translate error: {e}")
            return text  # Fallback to original
    
    async def _translate_deepl(self, text: str, source: str, target: str) -> str:
        """Translate using DeepL API"""
        try:
            import deepl
            import os
            
            auth_key = os.getenv("DEEPL_API_KEY")
            if not auth_key:
                return await self._translate_google(text, source, target)
            
            translator = deepl.Translator(auth_key)
            result = translator.translate_text(text, source_lang=source.upper(), target_lang=target.upper())
            return result.text
        except Exception as e:
            print(f"DeepL error: {e}")
            return await self._translate_google(text, source, target)
    
    async def _translate_azure(self, text: str, source: str, target: str) -> str:
        """Translate using Azure Translator API"""
        try:
            import os
            import requests
            
            key = os.getenv("AZURE_TRANSLATOR_KEY")
            endpoint = os.getenv("AZURE_TRANSLATOR_ENDPOINT")
            region = os.getenv("AZURE_TRANSLATOR_REGION", "global")
            
            if not key or not endpoint:
                return await self._translate_google(text, source, target)
            
            path = '/translate'
            constructed_url = endpoint + path
            
            params = {
                'api-version': '3.0',
                'from': source,
                'to': target
            }
            
            headers = {
                'Ocp-Apim-Subscription-Key': key,
                'Ocp-Apim-Subscription-Region': region,
                'Content-type': 'application/json'
            }
            
            body = [{'text': text}]
            
            response = requests.post(constructed_url, params=params, headers=headers, json=body)
            response.raise_for_status()
            
            result = response.json()
            return result[0]['translations'][0]['text']
        except Exception as e:
            print(f"Azure Translator error: {e}")
            return await self._translate_google(text, source, target)
    
    async def _translate_local(self, text: str, source: str, target: str) -> str:
        """Translate using local model (offline)"""
        try:
            from transformers import MarianMTModel, MarianTokenizer
            
            # Load model for language pair
            model_name = f'Helsinki-NLP/opus-mt-{source}-{target}'
            tokenizer = MarianTokenizer.from_pretrained(model_name)
            model = MarianMTModel.from_pretrained(model_name)
            
            # Translate
            inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
            outputs = model.generate(**inputs)
            translated = tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            return translated
        except Exception as e:
            print(f"Local translation error: {e}")
            return text  # Fallback to original
    
    async def translate_batch(self, texts: List[str], target_lang: str, source_lang: Optional[str] = None) -> List[Dict]:
        """
        Translate multiple texts
        
        Args:
            texts: List of texts to translate
            target_lang: Target language code
            source_lang: Source language code (auto-detect if None)
            
        Returns:
            List of translation results
        """
        results = []
        for text in texts:
            result = await self.translate(text, target_lang, source_lang)
            results.append(result)
        return results
    
    def get_supported_languages(self) -> List[Dict]:
        """Get list of supported languages"""
        return [
            {
                'code': code,
                'name': name,
                'native_name': self._get_native_name(code)
            }
            for code, name in self.language_names.items()
        ]
    
    def _get_native_name(self, code: str) -> str:
        """Get native language name"""
        native_names = {
            'en': 'English',
            'es': 'Español',
            'fr': 'Français',
            'de': 'Deutsch',
            'zh': '中文',
            'ja': '日本語',
            'ko': '한국어',
            'pt': 'Português',
            'ru': 'Русский',
            'ar': 'العربية',
            'hi': 'हिन्दी',
            'it': 'Italiano',
            'nl': 'Nederlands',
            'tr': 'Türkçe',
            'pl': 'Polski'
        }
        return native_names.get(code, code)
    
    async def translate_source(self, source: Dict, target_lang: str) -> Dict:
        """
        Translate source content
        
        Args:
            source: Source dictionary with title, text, etc.
            target_lang: Target language code
            
        Returns:
            Translated source dictionary
        """
        translated_source = source.copy()
        
        # Translate title
        if 'title' in source:
            title_result = await self.translate(source['title'], target_lang)
            translated_source['title'] = title_result['translated_text']
            translated_source['original_title'] = source['title']
        
        # Translate text content
        if 'text' in source:
            text_result = await self.translate(source['text'], target_lang)
            translated_source['text'] = text_result['translated_text']
            translated_source['original_text'] = source['text']
        
        # Add translation metadata
        translated_source['translation'] = {
            'target_language': target_lang,
            'source_language': title_result.get('source_language', 'en'),
            'provider': self.provider
        }
        
        return translated_source


# Singleton instance
translation_service = TranslationService()
