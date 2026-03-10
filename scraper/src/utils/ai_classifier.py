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
            "You are an expert lead classifier for home services. Your goal is to identify ACTUAL BUSINESS OPPORTUNITIES.\n"
            "Analyze the post and classify it into exactly one of these labels:\n\n"
            "1. 'buyer': The person is CATEGORICALLY seeking to HIRE or PAY for a service. They are asking for quotes, recommendations, or availability (e.g., 'Looking for a plumber', 'Any reliable painters in NYC?', 'Need my roof fixed').\n"
            "   - CRITICAL: Do NOT mark as buyer if they are just sharing a photo or telling a story.\n"
            "2. 'seller': The person is ADVERTISING a service (e.g., 'I offer affordable landscaping', 'Our team handles roofing', 'Check out our latest project').\n"
            "3. 'noise': Everything else. This includes:\n"
            "   - Art, history, or descriptive posts (e.g., 'A beautiful painting of NYC').\n"
            "   - Local news, lost pets, politics, or general community discussion.\n"
            "   - General questions that don't imply hiring (e.g., 'What color should I paint my room?').\n\n"
            "STRICT RULE: If a post is about a piece of ART or a HISTORY story, mark as 'noise' even if it mentions keywords like 'painting', 'building', or 'landscaping'.\n\n"
            "Return ONLY a JSON object: {\"label\": \"buyer\" | \"seller\" | \"noise\", \"confidence\": float (0.0 to 1.0), \"reason\": \"short reason\"}"
        )
        messages = [{
            "role": "system",
            "content": system_prompt
        }, {
            "role": "user",
            "content": f"Post Content to Classify: \"{text[:1200]}\""
        }]
        return self._call_api(messages)

def get_ai_classifier():
    return AIClassifier()
