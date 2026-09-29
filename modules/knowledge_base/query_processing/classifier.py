"""Query Classifier for Stage R9 Query Processing."""

import re
from typing import Dict, Optional
from core.interfaces.query_processor import IQueryClassifier
from core.schemas.query import QueryClassification


class QueryClassifier(IQueryClassifier):
    """
    Extensible query classification strategy that assigns functional categories
    (e.g., DIAGNOSIS_RELATED, PEST_DISEASE_RELATED, CROP_QUERY, SOIL_QUERY)
    based on keyword patterns in English and Indic scripts (Hindi, Marathi, etc.).
    """

    DIAGNOSIS_KEYWORDS = [
        "symptom", "disease", "yellowing", "wilting", "spot", "blight", "rot", "fungus", "virus",
        "bacterial", "infection", "treatment", "cure", "control", "spray", "pesticide", "fungicide",
        "रोग", "बीमारी", "कीट", "धब्बे", "सड़न", "झुलसा", "उपचार", "दवा", "छिड़काव", "रोकथाम", "लक्षण"
    ]

    PEST_KEYWORDS = [
        "pest", "insect", "bug", "worm", "caterpillar", "aphid", "whitefly", "borer", "beetle", "mite",
        "कीड़ा", "इल्ली", "माहू", "सफेद मक्खी", "सुंडी", "दीमक"
    ]

    SOIL_KEYWORDS = [
        "soil", "ph", "fertilizer", "manure", "nitrogen", "urea", "dap", "npk", "potash", "compost",
        "alkaline", "acidic", "saline", "nutrient", "deficiency",
        "मिट्टी", "भूमि", "खाद", "उर्वरक", "यूरिया", "डीएपी", "एनपीके", "पोषक तत्व", "कमी"
    ]

    CROP_KEYWORDS = [
        "variety", "sowing", "seed", "germination", "yield", "spacing", "irrigation", "water",
        "wheat", "rice", "paddy", "cotton", "maize", "sugarcane", "soybean", "mustard", "potato", "tomato",
        "किस्म", "बीज", "बुवाई", "सिंचाई", "गेहूँ", "धान", "कपास", "मक्का", "गन्ना", "सोयाबीन", "सरसों", "आलू", "टमाटर"
    ]

    WEATHER_KEYWORDS = [
        "weather", "rain", "temperature", "humidity", "frost", "drought", "monsoon",
        "मौसम", "बारिश", "तापमान", "सूखा", "पाला"
    ]

    FARM_PRACTICE_KEYWORDS = [
        "drip", "tillage", "mulching", "intercropping", "rotation", "organic", "polyhouse", "greenhouse",
        "ड्रिप", "मल्चिंग", "जैविक", "फसल चक्र"
    ]

    def classify(self, query_text: str, user_context: Optional[Dict] = None) -> QueryClassification:
        if not query_text:
            return QueryClassification.UNKNOWN

        q_lower = query_text.lower()

        # Check for diagnosis or pest/disease
        if any(kw in q_lower for kw in self.DIAGNOSIS_KEYWORDS):
            if any(kw in q_lower for kw in self.PEST_KEYWORDS):
                return QueryClassification.PEST_DISEASE_RELATED
            return QueryClassification.DIAGNOSIS_RELATED

        if any(kw in q_lower for kw in self.PEST_KEYWORDS):
            return QueryClassification.PEST_DISEASE_RELATED

        # Check for soil & nutrient
        if any(kw in q_lower for kw in self.SOIL_KEYWORDS):
            return QueryClassification.SOIL_QUERY

        # Check for weather
        if any(kw in q_lower for kw in self.WEATHER_KEYWORDS):
            return QueryClassification.WEATHER_RELATED

        # Check for farming practice
        if any(kw in q_lower for kw in self.FARM_PRACTICE_KEYWORDS):
            return QueryClassification.FARM_PRACTICE

        # Check for crop query
        if any(kw in q_lower for kw in self.CROP_KEYWORDS):
            return QueryClassification.CROP_QUERY

        # Default fallback
        if len(query_text.split()) > 3:
            return QueryClassification.AGRICULTURAL_GUIDANCE

        return QueryClassification.GENERAL_AGRICULTURE
