"""
buyer_intent.py — Advanced 5-tier lead classifier for Facebook scraping.

Tiers:
  5 = Urgent  (ASAP / emergency / no water-power)
  4 = Explicit need (need a plumber / looking for electrician)
  3 = Moderate / recommendation intent (any good plumber?)
  <3 = Low intent — filtered out by MIN_SCORE

The public API (is_buyer_request / get_detection_reason) is unchanged so all
existing callers continue to work without modification.
"""

import re
import sys
import os
from collections import defaultdict
from typing import Optional, Tuple

# Add src to path if needed for logger import
src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if src_dir not in sys.path:
    sys.path.append(src_dir)

try:
    from logger import ScraperLogger
except ImportError:
    try:
        from ..logger import ScraperLogger
    except ImportError:
        # Minimum fallback
        class ScraperLogger:
            def __init__(self, name): self.name = name
            def info(self, ev, **kw): print(f"INFO [{self.name}] {ev} {kw}")
            def debug(self, ev, **kw): print(f"DEBUG [{self.name}] {ev} {kw}")
            def error(self, ev, **kw): print(f"ERROR [{self.name}] {ev} {kw}")
            def exception(self, ev, **kw): print(f"EXCEPTION [{self.name}] {ev} {kw}")
            def warning(self, ev, **kw): print(f"WARNING [{self.name}] {ev} {kw}")

logger = ScraperLogger("buyer_intent")

# ── Minimum score to accept a lead ────────────────────────────────────────────
MIN_SCORE = 3

# ══════════════════════════════════════════════════════════════════════════════
#  US LOCATION FILTER
# ══════════════════════════════════════════════════════════════════════════════

US_CITIES = {
    "new york", "nyc", "brooklyn", "bronx", "queens", "manhattan", "staten island",
    "los angeles", "la", "san francisco", "san jose", "san diego", "fresno",
    "chicago", "houston", "phoenix", "philadelphia", "san antonio", "dallas",
    "austin", "jacksonville", "fort worth", "columbus", "charlotte", "indianapolis",
    "seattle", "denver", "washington dc", "nashville",
    "oklahoma city", "el paso", "boston", "las vegas", "memphis", "louisville",
    "portland", "baltimore", "milwaukee", "albuquerque", "tucson",
    "mesa", "sacramento", "atlanta", "kansas city", "omaha", "raleigh",
    "miami", "long beach", "virginia beach", "colorado springs", "tampa",
    "minneapolis", "new orleans", "cleveland", "honolulu", "anaheim",
    "lexington", "stockton", "pittsburgh", "st louis", "riverside",
    "jersey city", "newark", "hoboken", "buffalo", "rochester", "albany",
    "syracuse", "yonkers", "westbury", "candor", "levittown",
    "east syracuse", "forest hills", "parkchester",
    # MA / South Shore specific
    "hingham", "weymouth", "quincy", "braintree", "hull", "scituate",
    "cohasset", "marshfield", "duxbury", "norwell", "hanover",
    "birmingham",
}

US_STATES = {
    "alabama", "al", "alaska", "ak", "arizona", "az", "arkansas", "ar",
    "california", "ca", "colorado", "co", "connecticut", "ct", "delaware", "de",
    "florida", "fl", "georgia", "ga", "hawaii", "hi", "idaho", "id",
    "illinois", "il", "indiana", "in", "iowa", "ia", "kansas", "ks",
    "kentucky", "ky", "louisiana", "la", "maine", "me", "maryland", "md",
    "massachusetts", "ma", "michigan", "mi", "minnesota", "mn",
    "mississippi", "ms", "missouri", "mo", "montana", "mt", "nebraska", "ne",
    "nevada", "nv", "new hampshire", "nh", "new jersey", "nj", "new mexico", "nm",
    "new york", "ny", "north carolina", "nc", "north dakota", "nd", "ohio", "oh",
    "oklahoma", "ok", "oregon", "or", "pennsylvania", "pa", "rhode island", "ri",
    "south carolina", "sc", "south dakota", "sd", "tennessee", "tn", "texas", "tx",
    "utah", "ut", "vermont", "vt", "virginia", "va", "washington", "wa",
    "west virginia", "wv", "wisconsin", "wi", "wyoming", "wy",
    "washington dc", "d.c.", "dc",
}

NON_US_PATTERNS = [
    r"\bnorth york\b", r"\bgta\b", r"\btoronto\b", r"\bontario\b",
    r"\bvancouver\b", r"\bmontreal\b", r"\buk\b", r"\bunited kingdom\b",
    r"\blondon\b", r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b",
    r"\bindia\b", r"\bmumbai\b", r"\bdelhi\b", r"\bpakistan\b",
    r"\bkarachi\b", r"\blahore\b", r"\bphilippines\b", r"\bmanila\b",
    r"\bcanada\b", r"\bniagara\b",
    r"\bbirmingham,\s*uk\b", r"\bbirmingham,\s*england\b", r"\bwest midlands\b",
]

# ══════════════════════════════════════════════════════════════════════════════
#  EXCLUSION PATTERNS (service providers, ads, promos, hiring)
# ══════════════════════════════════════════════════════════════════════════════

EXCLUSION_PATTERNS = [
    r"\b(?:we|i)\s+(?:provide|offer|specialize|are\s+available|handle|serve|install|cover|just\s+completed|rewire|finished|understand|have\s+been\s+out|visited|busy|completed|worked)\b",
    r"\b(?:we've|we’ve|weve|i've|i’ve|ive)\s+(?:been|completed|just|finished)\b",
    r"\bour\s+(?:services?|team|company|business|work|clients?|licensed|technicians|experts|electricians|plumbers|painters|installations?)\b",
    r"\bi\s+(?:provide|offer|specialize|am\s+a\s+professional|run|do|handle|work\s+on|just\s+completed|rewired|installed)\b",
    r"\bmy\s+(?:company|business|name\s+is|services?|work)\b",
    r"\bcontact\s+(?:us|me)\s+(?:for|at|today|now)\b",
    r"\bcall\s+(?:us|me|now|today|for\s+a\s+quote|for\s+estimate)\b",
    r"\btext\s+(?:us|me)\b",
    r"\b(?:dm|message)\s+(?:us|me)\s+(?:for|to\s+book|to\s+schedule|today|more\s+info)\b",
    r"\b(?:free\s+)?(?:estimate|quote|consultation|assessment)\b",
    r"\b(?:fully|properly|highly|all|verified)\s+(?:insured|licensed|recommended|work\s+guaranteed|trained)\b",
    r"\blicensed\s+(?:and|&)?\s*insured\b",
    r"\b(?:licensed\s+)?master\s+(?:plumber|electrician)\b",
    r"\byears\s+of\s+experience\b",
    r"\bserving\s+(?:all|the|greater|your|area)\b",
    r"\bavailable\s+(?:for\s+work|in\s+your\s+area|24\s*/\s*7|around.the.clock|now)\b",
    r"\b24\s*(?:hour|hr|\/7)\s+(?:service|emergency|plumb|electric|call)\b",
    r"\bfast\s+(?:response|arrival|service|turnaround)\b",
    r"\bprofessional\s+(?:electrician|plumber|painter|contractor|service|work|installations?)\b",
    r"\b(?:apply|hiring|we.re\s+hiring|looking\s+to\s+hire|job\s+available)\b",
    r"\bjob\s+(?:opening|opportunity|available|listing)\b",
    r"\bintroduc(?:e|ing)\s+myself\b",
    r"\bi\s+just\s+joined\s+the\s+group\b",
    r"\b(?:#plumber|#electrician|#plumbing|#electrical|#painter|#cleaning|#contractor)\b",
    r"\b(?:call|text)\s*[:\-]?\s*\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b", # Phone number pattern
    r"\b(?:emergency\s+service\s+available)\b",
    r"\bhonest\s+(?:pricing|work|service)\b",
    r"\btrusted\s+(?:service|professional|contractor)\b",
    r"\breliable\s+(?:plumber|electrician|painter|contractor|service)\b",
    r"\b(?:same.day|next.day)\s+(?:service|repair|response)\b",
    r"\blooking\s+for\s+(?:side\s+)?work\b",
    r"\blooking\s+for\s+a\s+(?:side\s+)?gig\b",
    r"\bavailable\s+for\s+(?:side\s+)?work\b",
    r"\b(?:experienced|licensed)\s+(?:electrician|plumber|painter|handyman)\s+available\b",
    r"\bi\s+am\s+a\s+(?:residential|commercial)?\s*(electrician|plumber|painter|contractor|handyman)\b",
    r"\bi\s+handle\s+(?:small|all)\s+(?:service|job|work|repairs)\b",
    r"\bconnects\s+homeowners\b",
    r"\bwe'll\s+connect\s+you\b",
    r"\bcheck\s+out\s+(?:our|my)\s+(?:website|page|work)\b",
    r"\b(?:don't|do\s+not)\s+ignore\s+(?:these|signs)\b", # Informational/Clickbait
    r"\bis\s+your\s+home's?\b", # Informational/Ad
    r"\bsigns\s+you\s+may\s+need\b", # Informational/Ad
    r"\bdid\s+you\s+know\b", # Informational
    r"\bno\s+obligation\s+quote\b",
    r"\bget\s+in\s+touch\b",
    r"\ba\s+client\s+contacted\s+us\b",
    r"\bupon\s+inspection\b",
    r"\bare\s+standing\s+by\b",
    r"\bfire\s+risk\b",
    r"\bsafety\s+(?:hazard|risk)\b",
    r"\bhidden\s+signs\b",
    r"\bcommon\s+issue\b",
    r"\b(?:track|tracking)\s+down\b",
    r"\btricky\s+(?:faults|leaks|issues)\b",
    r"\btesting\s+electrical\s+installations\b",
    r"\bmaking\s+sure\s+properties\s+are\s+safe\b",
    r"\b(?:ltd|llc|inc|corp)\b",
    r"\bprevent\s+(?:bigger|expensive|safety)\b",
]

# ══════════════════════════════════════════════════════════════════════════════
#  BUYER INTENT TIERS
# ══════════════════════════════════════════════════════════════════════════════

URGENCY_PATTERNS = [
    r"\burgent(?:ly)?\b", r"\basap\b", r"\bright\s+(?:now|away)\b",
    r"\bimmediately\b", r"\bemergency\b", r"\btoday\b", r"\btonight\b",
    r"\bflooding\b", r"\bburst\s+pipe\b", r"\bno\s+(?:hot\s+)?water\b",
    r"\bno\s+(?:power|electricity)\b", r"\bshort\s+circuit\b",
    r"\bwater\s+damage\b", r"\boverflowing\b", r"\bgas\s+leak\b",
]

EXPLICIT_NEED_PATTERNS = [
    # Plumbing
    r"\bneed\s+(?:a\s+|an\s+)?plumber\b", r"\blooking\s+for\s+(?:a\s+|an\s+)?plumber\b",
    r"\bplumber\s+(?:needed|required|wanted)\b", r"\brequire\s+(?:a\s+|an\s+)?plumber\b",
    r"\bpipe\s+(?:is\s+)?(?:leaking|broken|burst|blocked)\b",
    r"\bwater\s+(?:leaking|leakage|damage)\b",
    r"\bdrain\s+(?:clogged|blocked|not\s+draining)\b",
    r"\btoilet\s+(?:overflowing|broken|not\s+flushing|clogged)\b",
    r"\bfaucet\s+(?:leaking|broken|dripping)\b",
    # Electrical
    r"\bneed\s+(?:a\s+|an\s+)?electrician\b", r"\blooking\s+for\s+(?:a\s+|an\s+)?electrician\b",
    r"\belectrician\s+(?:needed|required|wanted)\b",
    r"\brequire\s+(?:a\s+|an\s+)?electrician\b",
    r"\b(?:wiring|electrical)\s+(?:problem|issue|fault)\b",
    r"\boutlet\s+(?:not\s+working|dead|broken)\b",
    r"\bbreaker\s+(?:tripped|keeps\s+tripping|broken)\b",
    r"\blight\s+(?:not\s+working|flickering|broken)\b",
    # Painting
    r"\bneed\s+(?:a\s+|an\s+)?painter\b", r"\blooking\s+for\s+(?:a\s+|an\s+)?painter\b",
    r"\bneed\s+(?:my\s+)?(?:house|apartment|room|wall|ceiling)\s+painted\b",
    r"\bpainting\s+(?:job|work|done|needed)\b",
    # Carpentry
    r"\bneed\s+(?:a\s+|an\s+)?carpenter\b", r"\blooking\s+for\s+(?:a\s+|an\s+)?carpenter\b",
    r"\bfurniture\s+(?:repair|fix|broken)\b",
    r"\bwood\s+(?:floor|work|repair)\s+(?:needed|help|broken)\b",
    # Landscaping
    r"\bneed\s+(?:a\s+)?lawn\s+(?:care|service|mow)\b",
    r"\blooking\s+for\s+(?:a\s+)?landscaper\b",
    r"\bgarden\s+(?:cleanup|help|maintenance)\s+needed\b",
    # Cleaning
    r"\bneed\s+(?:a\s+)?(?:house|deep|home)\s+cleaning\b",
    r"\blooking\s+for\s+(?:a\s+)?cleaning\s+service\b",
    r"\bcleaner\s+needed\b",
    # Flooring
    r"\bneed\s+(?:flooring|floor|tile)\s+(?:installation|repair|help)\b",
    r"\blooking\s+for\s+(?:a\s+)?flooring\s+(?:contractor|company)\b",
    r"\bfloor\s+(?:broken|damaged|needs\s+repair)\b",
    # Fence
    r"\bneed\s+(?:a\s+)?fence\s+(?:installed|repaired|built)\b",
    r"\blooking\s+for\s+(?:a\s+)?fence\s+(?:contractor|company|installer)\b",
    # Asphalt
    r"\bneed\s+(?:driveway|asphalt|paving)\s+(?:repair|paving|help)\b",
    r"\blooking\s+for\s+(?:a\s+)?paving\s+contractor\b",
    # Renovation
    r"\bneed\s+(?:kitchen|bathroom|home)\s+renovation\b",
    r"\blooking\s+for\s+(?:a\s+)?(?:contractor|renovator)\b",
    r"\brenovation\s+(?:help|contractor|work)\s+needed\b",
    # Generic fix/repair
    r"\b(?:fix|repair|replace)\s+(?:my\s+)?(?:pipe|faucet|outlet|wiring|switch|breaker|floor|fence|driveway)\b",
]

MODERATE_INTENT_PATTERNS = [
    r"\brecommend\w*\s+(?:a\s+|an\s+)?(?:good\s+)?(?:plumber|electrician|painter|carpenter|landscaper|cleaner|contractor)\b",
    r"\bcan\s+(?:anyone|someone)\s+(?:recommend|suggest|help)\w*\b",
    r"\bknow\s+(?:any|a\s+good)\s+(?:plumber|electrician|painter|carpenter)\b",
    r"\b(?:any|good|reliable|affordable)\s+(?:plumber|electrician|painter|carpenter|cleaner)\s+(?:nearby|around|in)\b",
    r"\biso\s+(?:a\s+|an\s+)?(?:plumber|electrician|painter|carpenter|cleaner|contractor)\b",
    r"\b(?:plumbing|electrical|painting|carpentry|flooring|cleaning|landscaping)\s+(?:help|issue|work|repair)\b",
    r"\b(?:toilet|sink|shower|bathtub)\s+(?:not\s+working|broken|clogged|leaking)\b",
    r"\bwater\s+(?:pressure|heater|tank)\s+(?:issue|problem|broken|not\s+working)\b",
    r"\b(?:switch|socket)\s+(?:not\s+working|broken|dead)\b",
    r"\bany(?:one|body)\s+(?:know|have)\s+(?:a\s+|an\s+)?(?:good|reliable)?\s*(?:plumber|electrician|painter|contractor)\b",
    r"\bhelp\s+(?:with|finding)\s+(?:a\s+|an\s+)?(?:plumber|electrician|painter|contractor)\b",
    r"\bneed\s+(?:help|advice)\s+(?:with|for|about)\s+(?:plumbing|electrical|painting|renovation)\b",
]

ALL_BUYER_INTENT = URGENCY_PATTERNS + EXPLICIT_NEED_PATTERNS + MODERATE_INTENT_PATTERNS

# ══════════════════════════════════════════════════════════════════════════════
#  CATEGORY KEYWORD SETS
# ══════════════════════════════════════════════════════════════════════════════

CATEGORY_KEYWORDS = {
    "plumbing": {
        "plumber", "plumbing", "pipe", "piping", "leak", "leakage", "leaking",
        "drainage", "drain", "sewer", "faucet", "tap", "toilet", "sink",
        "bathtub", "shower", "water heater", "water tank", "water pressure",
        "clog", "clogged", "burst pipe", "flood", "flooding", "water line",
        "water damage", "no hot water",
    },
    "electrical": {
        "electrician", "electrical", "electric", "wiring", "wire", "switch",
        "outlet", "socket", "breaker", "fuse", "voltage", "power", "circuit",
        "short circuit", "tripped", "no power", "no electricity", "generator",
        "panel", "rewiring", "light fixture", "ceiling fan", "flickering",
        "electric panel", "knob and tube",
    },
    "painting": {
        "paint", "painter", "painting", "wall paint", "house painting",
        "interior paint", "exterior paint", "ceiling paint", "trim paint",
        "primer", "stucco", "repaint", "color",
    },
    "carpentry": {
        "carpenter", "carpentry", "woodwork", "wood work", "furniture repair",
        "cabinet", "door frame", "deck", "wood floor repair", "trim",
        "molding", "shelving", "built-in", "woodworking",
    },
    "landscaping": {
        "lawn", "lawn care", "garden", "gardening", "landscaping", "landscaper",
        "mowing", "mow", "hedge", "tree trimming", "mulch", "sod", "grass",
        "yard", "yard work", "sprinkler",
    },
    "cleaning": {
        "cleaning", "cleaner", "house cleaning", "deep cleaning", "home cleaning",
        "maid", "maid service", "housekeeping", "janitorial", "move-out clean",
        "spring cleaning", "carpet cleaning",
    },
    "flooring": {
        "flooring", "floor", "tile", "tiles", "hardwood", "laminate", "vinyl",
        "wood floor", "carpet", "subfloor", "grout", "floor installation",
        "floor repair", "tile installation",
    },
    "fence": {
        "fence", "fencing", "gate", "gate repair", "picket fence", "privacy fence",
        "chain link", "wood fence", "vinyl fence", "fence installation",
        "fence repair",
    },
    "asphalt": {
        "asphalt", "driveway", "paving", "pavement", "pothole", "blacktop",
        "driveway repair", "driveway paving", "asphalt paving", "crack seal",
        "parking lot",
    },
    "renovation": {
        "renovation", "remodel", "remodeling", "kitchen renovation",
        "bathroom renovation", "home improvement", "contractor", "gut renovation",
        "kitchen remodel", "bathroom remodel", "addition", "buildout",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def is_us_location(content: str) -> Tuple[bool, str]:
    """Return (is_us, detected_location). Rejects known non-US references."""
    norm = content.lower()
    for pattern in NON_US_PATTERNS:
        if re.search(pattern, norm):
            return False, ""
    for city in US_CITIES:
        if re.search(r"\b" + re.escape(city) + r"\b", norm):
            return True, city.title()
    for state in US_STATES:
        if re.search(r"\b" + re.escape(state) + r"\b", norm):
            return True, state.title()
    return False, ""


def score_lead(content: str) -> int:
    """
    5 = Urgent, 4 = Explicit need, 3 = Moderate / recommendation.
    Returns 1 if no buyer signal found (will be filtered by MIN_SCORE).
    """
    norm = _normalize(content)
    for p in URGENCY_PATTERNS:
        if re.search(p, norm):
            return 5
    for p in EXPLICIT_NEED_PATTERNS:
        if re.search(p, norm):
            return 4
    for p in MODERATE_INTENT_PATTERNS:
        if re.search(p, norm):
            return 3
    return 1


def classify_category(content: str) -> str:
    """Classify post into the best-matching service category."""
    norm = _normalize(content)
    scores = defaultdict(int)
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", norm):
                scores[category] += 1
    if not scores:
        return "other"
    return max(scores, key=lambda c: scores[c])


def _is_ollama_buyer_request(text: str, platform: str = "Facebook", location: str = "Unknown", verticals: str = "Home Services") -> dict:
    """Secondary gate: classified using Ollama (default qwen2.5:7b).
    
    Returns a dict with keys:
        is_lead (bool), category (str), intent_score (int), location (str)
    Defaults to FALSE on ANY error or parse failure.
    """
    logger.debug("ollama_qualification_started", text_preview=text[:150].replace("\n", " "))

    try:
        from config import get_settings
        settings = get_settings()

        ollama_url = settings.ollama_cloud_url.rstrip('/')
        if not ollama_url.endswith("/api/chat"):
            ollama_url += "/api/chat"

        ollama_model = getattr(settings, 'ollama_cloud_model', "qwen2.5:7b")

        # Strict prompt — requires exact JSON matches
        prompt = f"""You are a strict lead qualification system.

Your task is to analyze a Facebook post and determine if it is a REAL BUYER looking for a service.

Be VERY STRICT. Reject anything unclear.

---

Classify the post using these rules:

A post is a VALID LEAD ONLY IF:
- Person is clearly asking for a service
- Example: "need a plumber", "looking for electrician urgently"
- Must sound like a customer, NOT a business

---

REJECT if:
- Business promotion ("we provide", "contact us")
- Job posts ("hiring", "looking for workers")
- General discussion
- Recommendations without clear need
- Non-US or unclear location

---

Return ONLY JSON:

{{
  "is_lead": true/false,
  "category": "plumbing|electrical|other",
  "intent_score": 1-5,
  "location": "US|Non-US|Unknown"
}}

---

Scoring:
5 = urgent need ("need plumber ASAP")
4 = clear need ("looking for electrician")
3 = weak ("any recommendations?")
<=2 = reject

---

Post:
{text}
"""
        import requests
        import json

        payload = {
            "model": ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1}
        }

        resp = requests.post(ollama_url, json=payload, timeout=60)

        if resp.status_code != 200:
            logger.error("ollama_api_failed", status_code=resp.status_code, response=resp.text)
            return {
                "is_lead": False,
                "category": "other",
                "intent_score": 1,
                "location": "Unknown"
            }

        raw_response = resp.json()
        raw_content = raw_response.get("message", {}).get("content", "")
        logger.debug("ollama_raw_response_received", content=raw_content)

        try:
            parsed_result = json.loads(raw_content)
        except json.JSONDecodeError as e:
            logger.error("ollama_json_parse_failed", error=str(e), raw_content=raw_content)
            return {
                "is_lead": False,
                "category": "other",
                "intent_score": 1,
                "location": "Unknown"
            }

        # Safe defaults
        parsed_result["is_lead"] = parsed_result.get("is_lead") is True
        parsed_result["intent_score"] = int(parsed_result.get("intent_score", 1))
        parsed_result["location"] = str(parsed_result.get("location", "Unknown"))
        parsed_result["category"] = str(parsed_result.get("category", "other"))

        decision = "ACCEPTED" if parsed_result["is_lead"] else "REJECTED"
        logger.info("ollama_final_decision", decision=decision, result=parsed_result)
        return parsed_result

    except Exception as e:
        logger.exception("ollama_processing_exception", error=str(e))
        return {
            "is_lead": False,
            "category": "other",
            "intent_score": 1,
            "location": "Unknown"
        }


# ══════════════════════════════════════════════════════════════════════════════
#  GEMINI VALIDATION (Gate 7 — strict second-pass after Ollama)
# ══════════════════════════════════════════════════════════════════════════════

_GEMINI_PROMPT = """\
You are a highly strict lead validation AI.

Your job is to verify whether a social media post is from a REAL CUSTOMER who
wants to HIRE a service provider.

You must reject aggressively.

ACCEPT ONLY IF:
* A real person clearly needs help
* They intend to hire someone
* It is NOT a business advertisement
* It is NOT a job post
* It is NOT a recommendation request
* The location is in the United States

REJECT IF:
* Any form of promotion or marketing
* Any service provider offering services
* Any hiring or job-seeking post
* Any unclear or vague intent
* Any non-US or unknown location

STRICT RULE: If there is ANY doubt → return false

Return ONLY valid JSON (no markdown, no extra text):
{
  "is_valid_lead": true or false,
  "reason": "short explanation",
  "confidence": 0.0-1.0
}
"""


def validate_with_gemini(description: str) -> dict:
    """Strict second-pass validator using Google Gemini Flash.

    Only called after Ollama already classified the lead as qualified.
    Gemini is MORE strict than Ollama — one FALSE from Gemini = REJECT.

    Returns a dict with keys:
        is_valid_lead (bool), reason (str), confidence (float)
    Defaults to FALSE on ANY error, parse failure, or missing API key.
    """
    _reject = {"is_valid_lead": False, "reason": "default reject", "confidence": 0.0}

    if not description or len(description.strip()) < 10:
        logger.info("gemini_skip_empty_text")
        return {**_reject, "reason": "Text too short"}

    try:
        from config import get_settings
        settings = get_settings()
    except Exception as e:
        logger.error("gemini_config_load_failed", error=str(e))
        return {**_reject, "reason": "Config unavailable"}

    api_key = getattr(settings, "gemini_api_key", None) or os.getenv("GEMINI_API_KEY", "")
    model_name = getattr(settings, "gemini_model", None) or os.getenv("GEMINI_MODEL", "gemini-3.0-flash-preview")

    if not api_key:
        logger.warning("gemini_api_key_missing", action="skipping_gemini_gate",
                       note="Set GEMINI_API_KEY in .env to enable. Lead auto-rejected.")
        return {**_reject, "reason": "GEMINI_API_KEY not configured"}

    try:
        import google.generativeai as genai
        import json

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        prompt = f"{_GEMINI_PROMPT}\n\nPost:\n\"\"\"\n{description[:2000]}\n\"\"\""

        logger.debug("gemini_request_started", model=model_name,
                     text_preview=description[:120].replace("\n", " "))

        response = model.generate_content(prompt)
        raw_text = response.text.strip()

        logger.debug("gemini_raw_response", content=raw_text)

        # Strip optional markdown code fences
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as e:
            logger.error("gemini_json_parse_failed", error=str(e), raw=raw_text)
            return {**_reject, "reason": "Gemini JSON parse error"}

        # Strict boolean: any non-True value → False
        is_valid = parsed.get("is_valid_lead") is True
        result = {
            "is_valid_lead": is_valid,
            "reason": str(parsed.get("reason", "")),
            "confidence": float(parsed.get("confidence", 0.0)),
        }

        decision = "ACCEPTED" if is_valid else "REJECTED"
        logger.info("gemini_decision", decision=decision,
                    reason=result["reason"], confidence=result["confidence"])
        return result

    except ImportError:
        logger.error("gemini_sdk_missing",
                     detail="Run: pip install google-generativeai")
        return {**_reject, "reason": "google-generativeai not installed"}
    except Exception as e:
        logger.exception("gemini_api_exception", error=str(e))
        return {**_reject, "reason": f"Gemini exception: {e}"}


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API (unchanged interface)
# ══════════════════════════════════════════════════════════════════════════════

class BuyerIntentDetector:
    """
    Advanced lead classifier.

    Public API is backward-compatible:
      - is_buyer_request(text, require_url, url, custom_keywords, exclude_keywords, custom_indicators)
      - get_detection_reason(text, url)

    Internally uses the 5-tier scoring system + exclusion gate + US location filter.
    The `score_lead` and `classify_category` helpers are also importable for
    detailed enrichment (used in the GraphQL pipeline).
    """

    @classmethod
    def is_buyer_request(
        cls,
        text: str,
        require_url: bool = True,
        url: Optional[str] = None,
        custom_keywords: Optional[list] = None,
        exclude_keywords: Optional[list] = None,
        custom_indicators: Optional[list] = None,
    ) -> bool:
        """Return True only if the post passes ALL buyer-intent gates.
        
        Safe default: returns False on any unclear or failed check.
        """
        if not text or len(text.strip()) < 20:
            logger.info("prefilter_rejected", reason="too short (under 20 chars)")
            return False

        norm = _normalize(text)
        
        prefilter_words = ["we provide", "our services", "contact us", "dm", "call now", "hiring", "job", "apply", "we offer", "special offer", "free estimate"]
        for word in prefilter_words:
            if re.search(r"\b" + re.escape(word) + r"\b", norm):
                logger.info("prefilter_rejected", word=word)
                return False

        # Gate 0: Manual exclusion keywords (caller-supplied)
        if exclude_keywords:
            if any(k.lower().strip() in norm for k in exclude_keywords if k.strip()):
                return False

        # Gate 1: Exclusion patterns (service providers / ads / hiring)
        for pattern in EXCLUSION_PATTERNS:
            if re.search(pattern, norm):
                return False

        # Gate 2: Must contain genuine buyer intent (score >= MIN_SCORE)
        s = score_lead(text)
        if s < MIN_SCORE:
            return False

        # Gate 3: URL requirement (optional)
        if require_url and not url:
            return False

        # Gate 4: Vertical topic match (if custom_keywords supplied)
        if custom_keywords:
            topic_match = any(k.lower().strip() in norm for k in custom_keywords if k.strip())
            if not topic_match:
                return False

        # Gate 5: US location check — strict matching before AI
        # Must explicitly match a US city/state or be rejected as missing/ambiguous.
        full_content = f"{text} {url or ''}"
        is_us, loc_name = is_us_location(full_content)
        if not is_us:
            logger.info("location_rejected", reason="Failed explicit US city/state keyword check before AI")
            return False

        # Gate 6: Ollama AI — strictly check is_lead, intent_score, location
        ollama_result = _is_ollama_buyer_request(text)
        logger.info("ollama_result", result=ollama_result)
        if not ollama_result.get("is_lead", False):
            return False
        if ollama_result.get("intent_score", 0) < 4:
            logger.info("ollama_low_intent", score=ollama_result.get("intent_score"))
            return False
        if ollama_result.get("location") != "US":
            logger.info("ollama_non_us", location=ollama_result.get("location"))
            return False

        # Gate 7: Gemini strict second-pass — only runs if Ollama passed.
        # Gemini is MORE strict; a FALSE here = final REJECT.
        gemini_result = validate_with_gemini(text)
        logger.info("gemini_result", result=gemini_result)
        if not gemini_result.get("is_valid_lead", False):
            logger.info("gemini_rejected", reason=gemini_result.get("reason"))
            return False

        logger.info("lead_accepted", ollama_confidence=ollama_result.get("confidence"),
                    gemini_confidence=gemini_result.get("confidence"))
        return True

    @classmethod
    def get_detection_reason(cls, text: str, url: Optional[str] = None) -> str:
        """Return a human-readable reason for the classification decision."""
        if not text:
            return "Empty"

        norm = _normalize(text)

        for pattern in EXCLUSION_PATTERNS:
            if re.search(pattern, norm):
                return f"❌ Excluded (service provider / ad): matched '{pattern[:40]}'"

        s = score_lead(text)
        if s >= 5:
            reason = "✅ Buyer (Score 5 — Urgent)"
        elif s >= 4:
            reason = "✅ Buyer (Score 4 — Explicit need)"
        elif s >= 3:
            reason = "✅ Buyer (Score 3 — Recommendation intent)"
        else:
            return f"❌ No buyer intent (score={s}, min={MIN_SCORE})"

        # Check non-US patterns & enforce US keyword matching
        full_content = f"{text} {url or ''}"
        is_us, loc_name = is_us_location(full_content)
        if not is_us:
            return "❌ Location Rejected: Failed explicit US city/state keyword check before AI or found non-US pattern"

        # Check Ollama — strictly check is_lead, intent_score >= 4, location == "US"
        ollama_result = _is_ollama_buyer_request(text)
        if not ollama_result.get("is_lead"):
            return "❌ AI Rejected: Not classified as a buyer lead"
        if ollama_result.get("intent_score", 0) < 4:
            return f"❌ AI Rejected: Intent score too low ({ollama_result.get('intent_score')})"
        if ollama_result.get("location") != "US":
            return f"❌ AI Rejected: Location not confirmed as US ({ollama_result.get('location')})"

        # Check Gemini second pass
        gemini_result = validate_with_gemini(text)
        if not gemini_result.get("is_valid_lead"):
            return f"❌ Gemini Rejected: {gemini_result.get('reason', 'Failed strict validation')}"

        return reason


def get_buyer_intent_detector():
    return BuyerIntentDetector()