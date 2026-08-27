"""
Coğrafi Ağız Haritalayıcı (Geographical Dialect & Region Tagger)
Derleme sözlüğü ve ağız verilerini bölge ve il koordinatlarıyla etiketler.
"""
from typing import Any

GEO_REGIONS_MAP = {
    "Urfa": {"region": "Güneydoğu Anadolu", "lat": 37.1674, "lon": 38.7955},
    "Diyarbakır": {"region": "Güneydoğu Anadolu", "lat": 37.9144, "lon": 40.2306},
    "Adana": {"region": "Akdeniz", "lat": 37.0000, "lon": 35.3213},
    "Trabzon": {"region": "Doğu Karadeniz", "lat": 41.0027, "lon": 39.7168},
    "Erzurum": {"region": "Doğu Anadolu", "lat": 39.9043, "lon": 41.2679},
    "Kerkük": {"region": "Irak Türkmen Eli", "lat": 35.4681, "lon": 44.3922},
    "Tebriz": {"region": "Güney Azerbaycan", "lat": 38.0962, "lon": 46.2690},
    "Kırım": {"region": "Kırım Karay / Tatarları", "lat": 44.9521, "lon": 34.1024}
}

def tag_geographical_region(location_text: str) -> dict[str, Any]:
    txt = location_text.strip()
    for loc, info in GEO_REGIONS_MAP.items():
        if loc.lower() in txt.lower():
            return {
                "location": loc,
                "region": info["region"],
                "geo_coordinates": {"lat": info["lat"], "lon": info["lon"]}
            }
    return {"location": txt, "region": "Genel Türki Coğrafya", "geo_coordinates": None}
