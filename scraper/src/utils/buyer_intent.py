"""
Buyer Intent Detection Module
Detects buyer intent while filtering out promotional content.
"""

from typing import Optional
import re


class BuyerIntentDetector:
    """Detects whether a post is from a buyer looking to hire vs a seller promoting services."""
    
    BUYER_PATTERN = re.compile(
        r'(looking for|need|recommendation|can anyone recommend|who does|quote|estimate|contractor|'
        r'(anyone|can someone|does anyone|who do you|do you|any) (available|know|recommend|have|suggestions)|'
        r'iso|in search of|seeking|help with|suggestions for|referral for|looking to hire|'
        r'(who|anyone) (do|does|fix|install|repair)|'
        r'good (place|person|guy|crew|company) for|'
        r'recommend (a|an|some)|'
        r'price on|cost to|how much to)',
        re.IGNORECASE
    )
    
    SELLER_PATTERN = re.compile(
        r'(handyman|roofing|electrician|plumbing|painting|flooring|for sale|hiring|job|equipment|tools)|'
        r'(i |we )(offer|provide|do|can|am a|are a|specialize)|'
        r'(my|our) (company|business|team|services|work)|'
        r'(call|contact|dm|message|text|email) (me|us|today|now)|'
        r'(free (estimate|quote)|licensed and insured|years of experience|professional service|affordable|discount|book now|available now)|'
        r'looking for (work|projects|side work|new projects)|'
        r'(seeking|available for) (work|projects)|'
        r'(before you hire|look no further|give (me|us) a call)|'
        r'need (help|a plumber|a contractor)\?|'
        r'(24 hour|24/7|emergency (plumber|service)|asap service)|'
        r'(services available|for hire|now hiring|serving|appointments)|'
        r'(\$\d+)|(service (at|in))|(at your (home|location))|'
        r'(build a business|no upfront cost|join our team|become a (contractor|partner)|earn money|make money)|'
        r'(recruiting|opportunity|franchise|partnership|work with us|grow your business)',
        re.IGNORECASE
    )
    
    SERVICE_PATTERN = re.compile(
        r'(landscaping|landscape|landscaper|lawn care|lawn maintenance|lawn mowing|mowing|'
        r'yard cleanup|spring cleanup|fall cleanup|leaf removal|snow removal|snow plow|plowing|'
        r'yard work|lawn service|gardening|garden|mulch|trimming|hedge|tree service|'
        r'outdoor maintenance|property maintenance|'
        r'hardscape|hardscaping|pavers|patio|walkway|driveway|'
        r'retaining wall|stone wall|masonry|mason|brick|concrete|'
        r'backyard|front yard|fence|fencing|irrigation|sprinkler|sod|grass)',
        re.IGNORECASE
    )
    
    PHONE_PATTERN = re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b')
    COMPANY_PATTERN = re.compile(r'\b(asap|llc|inc|corp)\b', re.IGNORECASE)
    
    EXCLUSION_PATTERN = re.compile(
        r'\b(handyman|roofing|electrician|plumbing|painting|flooring|'
        r'for sale|hiring|job|equipment|tools|'
        r'career|interview|opportunity|benefits|salary|w2|1099)\b',
        re.IGNORECASE
    )
    
    @classmethod
    def is_buyer_request(cls, text: str, require_url: bool = True, url: Optional[str] = None, 
                         custom_keywords: Optional[list] = None,
                         exclude_keywords: Optional[list] = None,
                         custom_indicators: Optional[list] = None) -> bool:
        """
        Determine if a post is a buyer request vs seller promotion.
        """
        if not text:
            return False
        
        text_lower = text.lower().strip()
        
        buyer_pattern = cls.BUYER_PATTERN
        service_pattern = cls.SERVICE_PATTERN
        exclusion_pattern = cls.EXCLUSION_PATTERN
        
        if custom_keywords:
            kw_regex = '|'.join([re.escape(k.strip()) for k in custom_keywords if k.strip()])
            if kw_regex:
                buyer_pattern = re.compile(f'({kw_regex}|{cls.BUYER_PATTERN.pattern})', re.IGNORECASE)
                service_pattern = re.compile(f'({kw_regex}|{cls.SERVICE_PATTERN.pattern})', re.IGNORECASE)
        
        if exclude_keywords:
            ex_regex = '|'.join([re.escape(k.strip()) for k in exclude_keywords if k.strip()])
            if ex_regex:
                exclusion_pattern = re.compile(f'({ex_regex}|{cls.EXCLUSION_PATTERN.pattern})', re.IGNORECASE)

        if (cls.PHONE_PATTERN.search(text) or 
            cls.SELLER_PATTERN.search(text) or 
            cls.COMPANY_PATTERN.search(text) or
            exclusion_pattern.search(text)):
            return False
        
        if '?' in text_lower:
            parts = text_lower.split('?', 1)
            if len(parts) > 1 and any(w in parts[0] for w in ['need', 'want', 'looking']):
                if any(s in parts[1][:50] for s in ['we', 'call', 'contact', 'service', 'offer']):
                    return False
        
        for pronoun in ['i ', 'we ', 'my ', 'our ']:
            if pronoun in text_lower:
                for verb in ['do ', 'provide', 'offer', 'specialize', 'can help', 'am ', 'are ']:
                    idx1, idx2 = text_lower.find(pronoun), text_lower.find(verb)
                    if idx1 != -1 and idx2 != -1 and abs(idx1 - idx2) < 50:
                        return False
        
        if not buyer_pattern.search(text):
            return False
        
        if len(text_lower) < 20 and not service_pattern.search(text):
            return False
        
        # STRICT RELEVANCE CHECK:
        # Must match at least one service keyword (e.g. landscaping, pavers) 
        # OR a provided custom keyword.
        custom_kw_match = False
        if custom_keywords:
            kw_regex = '|'.join([re.escape(k.strip()) for k in custom_keywords if k.strip()])
            if kw_regex and re.search(kw_regex, text_lower):
                custom_kw_match = True
        
        if not custom_kw_match and not service_pattern.search(text):
            return False

        buyer_indicators = custom_indicators if custom_indicators else ['?', 'anyone', 'someone', 'who', 'canceled', 'urgent', 'asap']
        
        has_indicator = (any(ind.lower() in text_lower for ind in buyer_indicators) or 
                        re.search(r'looking for (a )?(mechanic|contractor|plumber|electrician|handyman|landscaper)', text_lower))
        
        if not has_indicator and not custom_kw_match:
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
            return f"Seller pattern: '{seller_match.group()[:30]}...'"
        
        if cls.COMPANY_PATTERN.search(text):
            return f"Company name pattern"
        
        buyer_match = cls.BUYER_PATTERN.search(text)
        if not buyer_match:
            return "No buyer intent keywords"
        
        # Check for buyer indicators
        buyer_indicators = ['?', 'anyone', 'someone', 'who', 'canceled', 'urgent', 'hiring', 'looking', 'need', 'recommendation']
        has_indicator = any(ind in text_lower for ind in buyer_indicators)
        if not has_indicator and not re.search(r'looking for (a )?(contractor|landscaper|worker|help)', text_lower):
            return "No question/request format/indicator"
        
        if not url:
            return f"Buyer keywords found but no URL"
        
        return f"✅ Buyer intent: '{buyer_match.group()[:40]}...'"