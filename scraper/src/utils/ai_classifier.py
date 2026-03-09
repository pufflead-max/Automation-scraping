import os
import json
import requests
from typing import Optional, Dict, Any

class AIClassifier:
    """Cloud-based AI Classification using Ollama Cloud API."""

    def __init__(self):
        try:
            try:
                from .config import get_settings
            except ImportError:
                from config import get_settings
            settings = get_settings()
            self.api_url = settings.ollama_cloud_url
            self.model = settings.ollama_cloud_model
        except (ImportError, ValueError, AttributeError):
            # Fallback values matching user environment
            self.api_url = "http://72.60.113.252:11434/api/chat"
            self.model = "gpt-oss:120b"

    def _call_api(self, messages: list) -> Dict[str, Any]:
        """Generic Ollama /api/chat caller returning JSON."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json"
        }
        try:
            response = requests.post(self.api_url, json=payload, timeout=20)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
            return json.loads(content)
        except Exception as e:
            return {"error": str(e), "label": "error", "confidence": 0}

    def classify_spam(self, text: str) -> Dict[str, Any]:
        """
        Classify if the post is spam or not_spam.
        As integrated by user for the initial version.
        """
        messages = [{
            "role": "system",
            "content": "Analyze the text and return only a JSON object: {\"label\": \"spam\" | \"not_spam\", \"confidence\": float}"
        }, {
            "role": "user",
            "content": f"Text: {text[:1000]}"
        }]
        return self._call_api(messages)

    def classify_intent(self, text: str) -> Dict[str, Any]:
        """
        Classify if the post is a buyer, seller, or noise.
        This extends the cloud classification to intent analysis.
        """
        messages = [{
            "role": "system",
            "content": "Analyze the Service/Post and determine if it's a BUYER (looking to hire), SELLER (offering service), or NOISE (unrelated). Return ONLY JSON: {\"label\": \"buyer\" | \"seller\" | \"noise\", \"confidence\": float, \"reason\": \"short_reason\"}"
        }, {
            "role": "user",
            "content": f"Post: {text[:1000]}"
        }]
        return self._call_api(messages)

def get_ai_classifier():
    return AIClassifier()
