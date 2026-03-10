import os
import json
import requests
from typing import Optional, Dict, Any, List

class AIClassifier:
    """Cloud-based AI Classification using Ollama Cloud API."""

    def __init__(self):
        self.api_url = os.getenv("OLLAMA_CLOUD_URL", "http://ollama:11434/api/chat")
        self.model = os.getenv("OLLAMA_CLOUD_MODEL", "qwen2.5:7b")
        
        # Try to load from settings if available, but don't fail if not
        try:
            try:
                from .config import get_settings
            except ImportError:
                from config import get_settings
            settings = get_settings()
            self.api_url = settings.ollama_cloud_url
            self.model = settings.ollama_cloud_model
        except:
            pass

    def _call_api(self, messages: list) -> Dict[str, Any]:
        """Generic Ollama /api/chat caller returning JSON."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json"
        }
        try:
            # Use docker service name 'ollama' if possible
            response = requests.post(self.api_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
            return json.loads(content)
        except Exception as e:
            # Fallback error response
            return {
                "is_qualified_lead": False, 
                "vertical": None, 
                "confidence": "low", 
                "reason": f"AI Error: {str(e)}"
            }

    def classify_lead(self, post_text: str, verticals: List[str], platform: str = "unknown", location: str = "unknown") -> Dict[str, Any]:
        """
        Single-prompt lead classification as requested by user.
        Determines if a post is from someone actively looking to HIRE a contractor in specific verticals.
        """
        verticals_str = "\n".join([f"- {v}" for v in verticals])

        system_prompt = (
            "You are a lead classification system for a home services contractor platform. "
            "Your job is to analyze social media posts and determine if the post is from someone "
            "actively looking to HIRE a contractor in one of the following service categories:\n\n"
            f"{verticals_str}\n\n"
            "Respond with a JSON object only, no other text:\n"
            "{\n"
            "  \"is_qualified_lead\": true/false,\n"
            "  \"vertical\": \"the matching vertical from the list or null\",\n"
            "  \"confidence\": \"high/medium/low\",\n"
            "  \"reason\": \"one sentence explanation\"\n"
            "}\n\n"
            "Classification rules:\n"
            "- TRUE only if the person is clearly looking to PAY someone to do the work (hiring intent)\n"
            "- FALSE if they are: offering their own services, selling products, sharing completed work, "
            "asking for advice/tips without hiring intent, posting about unrelated topics, or spam\n"
            "- A post about buying/selling physical items (e.g., a painting, furniture, tools) is NOT a service request\n"
            "- \"Looking for recommendations\" or \"anyone know a good [contractor type]\" = TRUE\n"
            "- \"I do [service], DM me\" = FALSE (this is a seller, not a buyer)"
        )

        user_message = (
            f"Classify this post:\n"
            f"Platform: {platform}\n"
            f"Location: {location}\n"
            f"Post: {post_text[:1500]}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        return self._call_api(messages)

    def classify_intent(self, text: str) -> Dict[str, Any]:
        """Legacy wrapper for backward compatibility."""
        # Use default verticals if not provided (for older code)
        verticals = ["Landscaping Services", "Painting Services", "Plumbing", "Electrical Services", "Carpentry Services"]
        res = self.classify_lead(text, verticals)
        return {
            "label": "buyer" if res.get("is_qualified_lead") else "noise",
            "confidence": 1.0 if res.get("confidence") == "high" else 0.5,
            "reason": res.get("reason"),
            "vertical": res.get("vertical")
        }

def get_ai_classifier():
    return AIClassifier()
