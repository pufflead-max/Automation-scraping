"""
Image OCR Utility
Extracts text from images using pytesseract to detect phone numbers
and business/company names that sellers embed in graphics.

This solves the case where a seller post slips through because their
phone number or business name is printed inside an image (not in the
scraped text body).
"""

import re
import io
import requests
from typing import Optional

try:
    from ..logger import get_logger
except ImportError:
    from logger import get_logger

logger = get_logger("image_ocr")

# ── Patterns to detect seller signals inside image text ──────────────────────
PHONE_IN_IMAGE = re.compile(
    r'(\+?1[\s.\-]?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})',
    re.IGNORECASE
)

COMPANY_IN_IMAGE = re.compile(
    r'\b(llc|inc|corp|co\.|ltd|services?|solutions?|cleaning|landscaping|'
    r'painting|plumbing|roofing|flooring|hvac|carpentry)\b',
    re.IGNORECASE
)

SELLER_IN_IMAGE = re.compile(
    r'\b(call|contact|dm|text|email|book|hire|available|licensed|insured|'
    r'certified|professional|affordable|free estimate|free quote|'
    r'years of experience|serving|we serve|now booking|www\.|\.com|@gmail)\b',
    re.IGNORECASE
)


def _load_pytesseract():
    """Lazy-load pytesseract to avoid import errors if not installed."""
    try:
        import pytesseract
        from PIL import Image
        return pytesseract, Image
    except ImportError:
        return None, None


def extract_text_from_image_url(image_url: str, timeout: int = 10) -> Optional[str]:
    """
    Downloads an image from a URL and extracts all visible text using OCR.
    Returns the extracted text string, or None if OCR fails or is unavailable.
    """
    pytesseract, Image = _load_pytesseract()
    if pytesseract is None:
        logger.debug("pytesseract_not_installed", msg="OCR skipped — install pytesseract + Pillow to enable")
        return None

    try:
        response = requests.get(image_url, timeout=timeout, stream=True)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")

        # OCR config: single block of text, optimized for mixed content
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(image, config=custom_config)
        extracted = text.strip()

        if extracted:
            logger.debug("ocr_extracted_text", image_url=image_url, char_count=len(extracted))
        return extracted if extracted else None

    except requests.exceptions.RequestException as e:
        logger.debug("ocr_image_download_failed", image_url=image_url, error=str(e))
        return None
    except Exception as e:
        logger.debug("ocr_extraction_failed", image_url=image_url, error=str(e))
        return None


def image_contains_seller_signals(image_url: str) -> dict:
    """
    Scans an image URL for seller signals (phone number, company name, seller keywords).
    
    Returns a dict:
    {
        "has_phone":    bool,
        "has_company":  bool,
        "has_seller":   bool,
        "is_seller":    bool,   # True if ANY seller signal found
        "ocr_text":     str     # Raw extracted text (for logging/debugging)
    }
    """
    result = {
        "has_phone": False,
        "has_company": False,
        "has_seller": False,
        "is_seller": False,
        "ocr_text": ""
    }

    if not image_url:
        return result

    ocr_text = extract_text_from_image_url(image_url)
    if not ocr_text:
        return result

    result["ocr_text"] = ocr_text
    result["has_phone"] = bool(PHONE_IN_IMAGE.search(ocr_text))
    result["has_company"] = bool(COMPANY_IN_IMAGE.search(ocr_text))
    result["has_seller"] = bool(SELLER_IN_IMAGE.search(ocr_text))
    result["is_seller"] = result["has_phone"] or (result["has_company"] and result["has_seller"])

    if result["is_seller"]:
        logger.info(
            "ocr_seller_detected_in_image",
            image_url=image_url,
            has_phone=result["has_phone"],
            has_company=result["has_company"],
            has_seller=result["has_seller"],
            preview=ocr_text[:120].replace("\n", " ")
        )

    return result


def scan_images_for_seller(image_urls: list) -> bool:
    """
    Scans a list of image URLs. Returns True immediately if ANY image
    is detected as containing seller signals (phone/business/offer keywords).
    This is the main entry point used by the scraper.
    """
    if not image_urls:
        return False

    for url in image_urls:
        if not url:
            continue
        scan = image_contains_seller_signals(url)
        if scan["is_seller"]:
            return True

    return False
