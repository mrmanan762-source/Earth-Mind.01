"""Agricultural Metadata Extractor for Stage R9 Query Processing."""

import re
from typing import Dict, Optional
from core.interfaces.query_processor import IQueryMetadataExtractor
from core.schemas.query import AgriculturalMetadata


class AgriculturalMetadataExtractor(IQueryMetadataExtractor):
    """
    Extracts explicit domain-specific agricultural metadata (crop, disease/pest,
    soil, region, season) from query text and upstream context.
    Strictly avoids hallucinating missing attributes—unsupported fields remain None.
    """

    CROPS_DICT = {
        "wheat": ["wheat", "गेहूँ", "गेहूं", "कनक"],
        "rice": ["rice", "paddy", "धान", "चावल"],
        "cotton": ["cotton", "कपास", "रूई"],
        "maize": ["maize", "corn", "मक्का"],
        "sugarcane": ["sugarcane", "गन्ना"],
        "soybean": ["soybean", "सोयाबीन"],
        "mustard": ["mustard", "सरसों", "राई"],
        "potato": ["potato", "आलू"],
        "tomato": ["tomato", "टमाटर"],
        "onion": ["onion", "प्याज़", "कांदा"],
        "chilli": ["chilli", "chili", "मिर्च"],
        "banana": ["banana", "केला"],
        "apple": ["apple", "सेव", "सेब"],
        "mango": ["mango", "आम"]
    }

    DISEASES_PESTS_DICT = {
        "yellow_rust": ["yellow rust", "stripe rust", "पीला रतुआ", "पीला रोली"],
        "brown_rust": ["brown rust", "leaf rust", "भूरा रतुआ"],
        "blight": ["blight", "late blight", "early blight", "झुलसा", "अंगमारी"],
        "wilt": ["wilt", "fusarium wilt", "उकठा", "मुरझान"],
        "powdery_mildew": ["powdery mildew", "छछिया", "सफेद चूर्ण"],
        "downy_mildew": ["downy mildew", "मृदुरोमिल आसिता"],
        "aphid": ["aphid", "aphids", "माहू", "चेपा"],
        "whitefly": ["whitefly", "whiteflies", "सफेद मक्खी"],
        "stem_borer": ["stem borer", "तना छेदक"],
        "fall_armyworm": ["fall armyworm", "armyworm", "फॉल्स आर्मीवर्म", "सैनिक इल्ली"],
        "termite": ["termite", "termites", "दीमक"]
    }

    SOILS_DICT = {
        "black_cotton": ["black soil", "black cotton soil", "काली मिट्टी", "रेगुर"],
        "alluvial": ["alluvial soil", "जलोढ़ मिट्टी", "दूमट"],
        "red_soil": ["red soil", "लाल मिट्टी"],
        "laterite": ["laterite soil", "लैटेराइट"],
        "sandy": ["sandy soil", "बलुई मिट्टी", "रेतली"]
    }

    SOIL_CONDITIONS_DICT = {
        "acidic": ["acidic", "acid soil", "अम्लीय"],
        "alkaline": ["alkaline", "alkali", "क्षारीय"],
        "saline": ["saline", "salinity", "लवणीय"]
    }

    SEASONS_DICT = {
        "kharif": ["kharif", "monsoon season", "खरीफ"],
        "rabi": ["rabi", "winter season", "रबी"],
        "zaid": ["zaid", "summer season", "जायद"]
    }

    CROP_STAGES_DICT = {
        "sowing": ["sowing", "germination", "seeding", "बुवाई", "अंकुरण"],
        "vegetative": ["vegetative", "tillering", "शाकीय वृद्धि", "कल्ले निकलना"],
        "flowering": ["flowering", "blooming", "पुष्पन", "फूल आना"],
        "fruiting": ["fruiting", "pod formation", "grain filling", "फल आना", "दाना भरना"],
        "harvest": ["harvest", "harvesting", "कटाई", "पकाई"]
    }

    REGIONS_DICT = {
        "punjab": ["punjab", "पंजाब"],
        "haryana": ["haryana", "हरियाणा"],
        "uttar_pradesh": ["uttar pradesh", "up", "उत्तर प्रदेश"],
        "madhya_pradesh": ["madhya pradesh", "mp", "मध्य प्रदेश"],
        "maharashtra": ["maharashtra", "महाराष्ट्र"],
        "rajasthan": ["rajasthan", "राजस्थान"],
        "gujarat": ["gujarat", "गुजरात"],
        "bihar": ["bihar", "बिहार"],
        "karnataka": ["karnataka", "कर्नाटक"],
        "andhra_pradesh": ["andhra pradesh", "आंध्र प्रदेश"],
        "telangana": ["telangana", "तेलंगाना"],
        "tamil_nadu": ["tamil nadu", "तमिलनाडु"],
        "punjab_haryana_plain": ["indo-gangetic plain", "gangetic plain"]
    }

    def extract(self, query_text: str, user_context: Optional[Dict] = None) -> AgriculturalMetadata:
        ctx = user_context or {}
        q_lower = (query_text or "").lower()

        crop = ctx.get("crop")
        if not crop and q_lower:
            crop = self._match_dict(q_lower, self.CROPS_DICT)

        crop_stage = ctx.get("crop_stage")
        if not crop_stage and q_lower:
            crop_stage = self._match_dict(q_lower, self.CROP_STAGES_DICT)

        disease_pest = ctx.get("disease_pest") or ctx.get("disease") or ctx.get("pest")
        if not disease_pest and q_lower:
            disease_pest = self._match_dict(q_lower, self.DISEASES_PESTS_DICT)

        soil_type = ctx.get("soil_type")
        if not soil_type and q_lower:
            soil_type = self._match_dict(q_lower, self.SOILS_DICT)

        soil_condition = ctx.get("soil_condition")
        if not soil_condition and q_lower:
            soil_condition = self._match_dict(q_lower, self.SOIL_CONDITIONS_DICT)

        region = ctx.get("region")
        if not region and q_lower:
            region = self._match_dict(q_lower, self.REGIONS_DICT)

        state = ctx.get("state")
        district = ctx.get("district")

        season = ctx.get("season")
        if not season and q_lower:
            season = self._match_dict(q_lower, self.SEASONS_DICT)

        farming_practice = ctx.get("farming_practice")
        topic = ctx.get("topic")
        time_range = ctx.get("time_range")

        return AgriculturalMetadata(
            crop=crop,
            crop_stage=crop_stage,
            disease_pest=disease_pest,
            soil_type=soil_type,
            soil_condition=soil_condition,
            region=region,
            state=state,
            district=district,
            season=season,
            farming_practice=farming_practice,
            topic=topic,
            time_range=time_range,
        )

    def _match_dict(self, text: str, mapping: Dict[str, list]) -> Optional[str]:
        for canonical, aliases in mapping.items():
            for alias in aliases:
                # Word-boundary or substring check
                pattern = r'\b' + re.escape(alias) + r'\b' if alias.isascii() else re.escape(alias)
                if re.search(pattern, text):
                    return canonical
        return None
