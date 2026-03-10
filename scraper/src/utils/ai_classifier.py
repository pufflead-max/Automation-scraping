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
            self.api_url = "http://localhost:11434/api/chat"
            self.model = "qwen2.5:7b"

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

    def classify_intent(self, text: str) -> Dict[str, Any]:
        """
        Classify if the post is a buyer, seller, or noise.
        Fine-tuned prompt to ensure accurate buyer intent detection.
        """
        system_prompt = (
            "You are an expert lead classifier for home services. Analyze the post and classify it into exactly one of these labels:\n"
            "1. 'buyer': The person writing the post is ACTIVELY LOOKING TO HIRE someone or get quotes/recommendations for a service they need done (e.g. 'I need a plumber', 'Looking for recommendations for a landscaper', 'Who can fix my roof').\n"
            "2. 'seller': The person writing the post is ADVERTISING their own business or offering to do work for others (e.g. 'I do landscaping', 'Call me for a free quote', 'Hire us').\n"
            "3. 'noise': Unrelated posts, news, spam, lost pets, or just generic questions not related to hiring.\n\n"
            "Return ONLY a JSON object: {\"label\": \"buyer\" | \"seller\" | \"noise\", \"confidence\": float (0.0 to 1.0), \"reason\": \"short reason\"}"
        )
        messages = [{
            "role": "system",
            "content": system_prompt
        }, {
            "role": "user",
            "content": f"Post: {text[:1000]}"
        }]
        return self._call_api(messages)

def get_ai_classifier():
    return AIClassifier()
