"""
Türki Diller Morfolojik Analizör ve Akıllı Kök Ayrıştırıcı (Turkic Stemmer & Morphological Analyzer)
Karmaşık türemiş ve çekim ekli kelimeleri köklerine ayrıştırır. Alıntı kelimelerde yapay ek kesimini engeller.
"""

# Öz Türkçede söz başında KESİNLİKLE bulunmayan (veya aşırı nadir olan) ünsüzler
NON_TURKIC_INITIAL_CONSONANTS = ['f', 'h', 'p', 'v', 'j', 'z']

# Türkçe ve Türki diller yapım ve çekim ekleri
TURKIC_SUFFIXES = [
    "cılık", "cilik", "çılık", "çilik", "culuk", "cülük",
    "daş", "deş", "taş", "teş",
    "lik", "lık", "luk", "lük", "ci", "cı", "cu", "cü", "çi", "çı",
    "li", "lı", "lu", "lü",
    "siz", "sız", "suz", "süz",
    "gi", "gı", "gu", "gü", "ki", "kı", "ku", "kü",
    "sel", "sal", "gil",
    "ler", "lar", "dan", "den", "tan", "ten",
    "daki", "deki", "taki", "teki",
    "mak", "mek", "ma", "me", "ış", "iş", "uş", "üş"
]

def analyze_morphology(word: str) -> tuple[str, list[str]]:
    w = word.strip().lower()

    # 1. Alıntı Kelime Koruması: f-, h-, p-, v-, j-, z- ile başlayan kelimelerde mekanik ek kesimi yapma!
    if w and w[0] in NON_TURKIC_INITIAL_CONSONANTS:
        return w, []

    detected_suffixes = []
    stem = w

    # 2. Mekanik ek kesimi (sadece geçerli Öz Türkçe kök adayları için)
    for suf in TURKIC_SUFFIXES:
        if stem.endswith(suf) and len(stem) - len(suf) >= 3:
            detected_suffixes.append("-" + suf)
            stem = stem[:-len(suf)]

    return stem, detected_suffixes
