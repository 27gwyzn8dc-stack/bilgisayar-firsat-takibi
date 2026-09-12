"""Başlık benzerliği değil, üreticinin tam parça koduyla eşleştirme."""
import re

def component_key(title):
    text = title.upper()
    # Notebook belleği/depolaması yükseltilmiş olabilir; bu kodlar yalnız parçalar içindir.
    if re.search(r'LAPTOP|NOTEBOOK|DİZÜSTÜ|MASAÜSTÜ|MACBOOK', text): return ''
    patterns = {
        'asus': r'\b90YV[A-Z0-9]{4}-[A-Z0-9]{6}\b',
        'corsair': r'\bCM[HKWTSK][A-Z0-9]{5,25}\b',
        'kingston': r'\bKF[345][A-Z0-9]{5,20}(?:/[0-9]{1,3})?\b',
        'samsung': r'\bMZ-[A-Z0-9]{5,15}\b',
        'wd': r'\bWDS[0-9A-Z]{5,20}\b',
        'crucial': r'\bCT[0-9][A-Z0-9]{5,20}\b',
    }
    for brand, pattern in patterns.items():
        match = re.search(pattern, text)
        if match: return 'mpn:'+brand+':'+match[0]
    return ''
