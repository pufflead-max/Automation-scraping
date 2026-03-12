"""
Buyer Intent Detection Module
Detects buyer intent while filtering out promotional content.

KEY DESIGN PRINCIPLE:
  custom_keywords determine TOPIC RELEVANCE (does the post relate to the user's service?).
  BUYER_PATTERN / buyer indicators determine INTENT (is someone asking to hire?).
  These two checks are kept SEPARATE — merging them caused seller posts to pass detection.
"""

from typing import Optional
import re


class BuyerIntentDetector:
    """Detects whether a post is from a buyer looking to hire vs a seller promoting services."""

    # ── Buyer signals: post is from someone who wants to HIRE ──────────────────
    BUYER_PATTERN = re.compile(
        r'(looking for|need|recommendation|can anyone recommend|who does|quote|estimate|'
        r'(anyone|can someone|does anyone|who do you|do you|any) (available|know|recommend|have|suggestions)|'
        r'iso|in search of|seeking help|suggestions for|referral for|looking to hire|'
        r'(who|anyone) (do|does|fix|install|repair|clean)|'
        r'good (place|person|guy|crew|company|service) for|'
        r'recommend (a|an|some)|'
        r'price on|cost to|how much (to|does|would|for)|'
        r'anyone (available|know|recommend|doing)|'
        r'can (you|anyone|someone) (help|recommend|fix|install|do)|'
        r'need (help|someone|a (contractor|company|crew|person|professional|service))|'
        r'looking for (a |an )?(good|reliable|affordable|local)?'
        r'(contractor|landscaper|painter|plumber|company|crew|handyman|carpenter|cleaner|flooring|service))',
        re.IGNORECASE
    )

    # ── Hard seller signals: post is from someone OFFERING a service ────────────
    # Also includes irrelevant content categories like obituaries.
    SELLER_PATTERN = re.compile(
        r'(for sale|equipment|tools|supplies)\b|'
        r'\b(i |we )(offer|provide|do |can |am a|are a|specialize|started a)\b|'
        r'\b(my|our) (company|business|team|services|work|shop)\b|'
        r'\b(call|contact|dm|message|text|email) (me|us|today|now|for (details|info))\b|'
        r'\b(free (estimate|quote|consultation)|licensed and insured|years of experience|'
        r'professional service|affordable rates?|discount|book now|available now|'
        r'fully insured|bonded and insured)\b|'
        r'\blooking for (work|projects|side work|new (projects|clients|opportunities))\b|'
        r'\b(seeking|available for) (work|projects)\b|'
        r'\b(before you hire|look no further|give (me|us) a call|check out my)\b|'
        r'\b(24 hour|24/7|emergency service|asap service)\b|'
        r'\b(services available|for hire|now hiring|serving|appointments available|accepting new)\b|'
        r'\bat your (home|location|door)\b|'
        r'\b(build a business|no upfront cost|join our team|earn money|make money)\b|'
        r'\b(recruiting|franchise|partnership|work with us|grow your business)\b|'
        r'\bwe (serve|cover|specialize|do)\b|'
        r'\b(starting at|rates? (start|from|as low))\b|'
        r'\b(obituary|funeral|passing of|memorial service|celebration of life|deepest condolences|'
        r'in memory of|rest in peace|passed away)\b|'
        # ── Rhetorical seller openers: seller fakes a buyer question then pitches ──
        r'looking for a (dependable|reliable|professional|trusted|affordable|quality|great|top)'
        r'\s+(cleaning|landscaping|painting|plumbing|handyman|roofing|flooring|moving|hvac)\s+service|'
        r'\b(\w+\s+){0,3}(provides?|delivers?|offers?) (high.quality|professional|reliable|affordable|quality)|'
        r'\b(\w+ (cleaning|landscaping|painting|services?|solutions?))\s+(provides?|offers?|specializes?|delivers?)\b|'
        r'\bservices? offered\b|'
        r'\b(we are|i am|we\'re|i\'m) (a |an )?(professional|licensed|insured|certified|experienced)\b',
        re.IGNORECASE
    )

    # ── Service topic keywords (relevance check) ─────────────────────────────────
    SERVICE_PATTERN = re.compile(
        r'\b(landscaping|landscape|landscaper|lawn care|lawn maintenance|lawn mowing|mowing|'
        r'yard cleanup|spring cleanup|fall cleanup|leaf removal|snow removal|snow plow|plowing|'
        r'yard work|lawn service|gardening|garden|mulch|trimming|hedge|tree service|'
        r'outdoor maintenance|property maintenance|'
        r'hardscape|hardscaping|pavers|patio|walkway|driveway|'
        r'retaining wall|stone wall|masonry|mason|brick|concrete|'
        r'backyard|front yard|fence|fencing|irrigation|sprinkler|sod|grass|'
        r'painting|painter|paint job|interior paint|exterior paint|'
        r'flooring|hardwood floor|tile|carpet|laminate|'
        r'carpentry|carpenter|woodwork|cabinet|deck|'
        r'cleaning|house cleaning|maid service|deep clean)\b',
        re.IGNORECASE
    )

    # ── Hard signals that confirm BUYER intent (question/request words) ──────────
    STRONG_BUYER_INDICATORS = re.compile(
        r'\b(need|needed|needs|looking for|want|wanted|wants|'
        r'anyone|someone|recommend|recommendation|'
        r'help with|help me|can anyone|does anyone|who (does|can|knows)|'
        r'iso|in search of|seeking|referral|quote|estimate|'
        r'how much|what does it cost|price for|searching for|'
        r'urgent|asap|emergency|soon|quickly)\b',
        re.IGNORECASE
    )

    PHONE_PATTERN = re.compile(r'\b\d{3}[-.\\s]?\d{3}[-.\\s]?\d{4}\b')
    COMPANY_PATTERN = re.compile(r'\b(llc|inc|corp|co\.|ltd)\b', re.IGNORECASE)

    @classmethod
    def is_buyer_request(cls, text: str, require_url: bool = True, url: Optional[str] = None,
                         custom_keywords: Optional[list] = None,
                         exclude_keywords: Optional[list] = None,
                         custom_indicators: Optional[list] = None) -> bool:
        """
        Determine if a post is a buyer request vs seller promotion.

        Logic flow:
        1. Hard reject if phone, seller pattern, company suffix, or exclude keyword found.
        2. Hard require: must match STRONG_BUYER_INDICATORS (the post must *ask* for something).
        3. Relevance check: post must relate to the user's service area via SERVICE_PATTERN or custom_keywords.
        4. Double-check: no seller-speak hiding in first-person phrases.
        """
        if not text or len(text.strip()) < 5:
            return False

        text_lower = text.lower().strip()

        # ── Build custom exclusion pattern ────────────────────────────────────
        exclusion_pattern = None
        if exclude_keywords:
            ex_regex = '|'.join([r'\b' + re.escape(k.strip()) + r'\b' for k in exclude_keywords if k.strip()])
            if ex_regex:
                exclusion_pattern = re.compile(ex_regex, re.IGNORECASE)

        # ── STEP 1: Hard rejects ──────────────────────────────────────────────
        if cls.PHONE_PATTERN.search(text):
            return False
        if cls.SELLER_PATTERN.search(text):
            return False
        if cls.COMPANY_PATTERN.search(text):
            return False
        if exclusion_pattern and exclusion_pattern.search(text):
            return False

        # ── STEP 2: Must have a strong buyer signal ──────────────────────────
        # Check both the built-in STRONG_BUYER_INDICATORS and the BUYER_PATTERN
        has_buyer_signal = (
            cls.STRONG_BUYER_INDICATORS.search(text) or
            cls.BUYER_PATTERN.search(text)
        )
        # For custom_indicators, treat them as additional strong buyer signals
        if custom_indicators and not has_buyer_signal:
            has_buyer_signal = any(ind.lower() in text_lower for ind in custom_indicators)

        if not has_buyer_signal:
            return False

        # ── STEP 3: Must be topically relevant ──────────────────────────────
        topic_match = bool(cls.SERVICE_PATTERN.search(text))
        if custom_keywords and not topic_match:
            kw_regex = '|'.join([r'\b' + re.escape(k.strip()) + r'\b' for k in custom_keywords if k.strip()])
            if kw_regex:
                topic_match = bool(re.search(kw_regex, text_lower, re.IGNORECASE))

        if not topic_match:
            return False

        # ── STEP 4: Reject first-person seller phrases ────────────────────────
        for pronoun in ['i ', 'we ', 'my ', 'our ']:
            if pronoun in text_lower:
                for verb in ['provide', 'offer', 'specialize', 'can help', 'serve', 'do work', 'cover']:
                    idx1 = text_lower.find(pronoun)
                    idx2 = text_lower.find(verb)
                    if idx1 != -1 and idx2 != -1 and abs(idx1 - idx2) < 60:
                        return False

        return not require_url or bool(url)

    @classmethod
    def get_detection_reason(cls, text: str, url: Optional[str] = None) -> str:
        """Get human-readable reason for classification."""
        if not text:
            return "Empty text"

        text_lower = text.lower()

        if cls.PHONE_PATTERN.search(text):
            return "Contains phone number (seller)"

        seller_match = cls.SELLER_PATTERN.search(text)
        if seller_match:
            return f"Seller pattern: '{seller_match.group()[:35]}'"

        if cls.COMPANY_PATTERN.search(text):
            return "Company suffix (LLC/Inc/Corp)"

        buyer_match = cls.BUYER_PATTERN.search(text) or cls.STRONG_BUYER_INDICATORS.search(text)
        if not buyer_match:
            return "No buyer intent / request signal"

        if not cls.SERVICE_PATTERN.search(text):
            return "No relevant service keyword topic"

        if not url:
            return "Buyer signal found but no URL"

        return f"✅ Buyer intent: '{buyer_match.group()[:40]}'"