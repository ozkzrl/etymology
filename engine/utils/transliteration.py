"""
Türki Diller Otomatik Alfabe ve Transkripsiyon Çevirici (Transliteration Engine)
Kiril, Arap ve Orhun Göktürk Alfabesini Latin Fonetik Okunuşuna Çevirir.
"""
import re

CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ғ": "ğ", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "қ": "q", "л": "l", "м": "m",
    "н": "n", "ң": "ñ", "о": "o", "ө": "ö", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ү": "ü", "ф": "f", "х": "h", "һ": "h", "ц": "ts", "ч": "ç", "ш": "ş",
    "щ": "şç", "ъ": "", "ы": "ı", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ә": "ə", "і": "i", "ҫ": "ś", "ӳ": "ü", "ӑ": "ă", "ӗ": "ĕ"
}

ARABIC_TO_LATIN = {
    "ا": "a", "ب": "b", "پ": "p", "ت": "t", "ث": "s", "ج": "c", "چ": "ç", "ح": "h",
    "خ": "h", "د": "d", "ذ": "z", "ر": "r", "ز": "z", "ژ": "j", "س": "s", "ش": "ş",
    "ص": "s", "ض": "z", "ط": "t", "ظ": "z", "ع": "a", "غ": "ğ", "ف": "f", "ق": "q",
    "ک": "k", "گ": "g", "ڭ": "ñ", "ل": "l", "م": "m", "ن": "n", "و": "v", "ه": "h",
    "ی": "y", "ي": "y", "ئ": "e", "ە": "e", "ۇ": "u", "ۈ": "ü", "ۆ": "ö", "ى": "ı"
}

def transliterate_to_latin(text: str) -> str:
    if not text:
        return text

    # Eğer zaten Latin harfleri ağırlıklıysa dokunma
    if not re.search(r'[\u0400-\u04FF\u0600-\u06FF]', text):
        return text

    res = []
    for ch in text:
        ch_lower = ch.lower()
        if ch_lower in CYRILLIC_TO_LATIN:
            trans = CYRILLIC_TO_LATIN[ch_lower]
            res.append(trans.upper() if ch.isupper() else trans)
        elif ch_lower in ARABIC_TO_LATIN:
            res.append(ARABIC_TO_LATIN[ch_lower])
        else:
            res.append(ch)

    return "".join(res)
