"""
Macedonian Cyrillic -> Latin, for comparing ad titles across scripts.

Sellers write the same thing as "Самсунг", "Samsung", "зачуван", "zachuvan"
or "zacuvan". TF-IDF over the raw text sees Cyrillic and Latin titles as
sharing almost nothing, so the agents bring every title into one script
first. (The frontend's formatTitle.js goes the other way, Latin to Cyrillic,
only for display.)

to_latin()      standard transliteration (ж->zh, ш->sh, ч->ch, ќ->kj ...),
                the spelling most sellers use; readable, so cluster labels
                built from it still look like words.
fold_variants() additionally folds the spellings sellers mix (zh/z/ž -> z,
                sh/s/š -> s, ch/c/č -> c, kj/ć/ќ -> k, gj/đ/ѓ -> g), for
                matching only.
"""
import re

_CYR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'ѓ': 'gj', 'е': 'e',
    'ж': 'zh', 'з': 'z', 'ѕ': 'dz', 'и': 'i', 'ј': 'j', 'к': 'k', 'л': 'l',
    'љ': 'lj', 'м': 'm', 'н': 'n', 'њ': 'nj', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'ќ': 'kj', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c',
    'ч': 'ch', 'џ': 'dzh', 'ш': 'sh',
    # Serbian/Russian letters that turn up in titles too
    'ђ': 'gj', 'ћ': 'kj', 'й': 'j', 'ы': 'y', 'э': 'e', 'ю': 'ju', 'я': 'ja',
    'щ': 'sh', 'ъ': '', 'ь': '', 'ё': 'e',
}

_FOLD = [
    ('dzh', 'dz'), ('zh', 'z'), ('sh', 's'), ('ch', 'c'), ('kj', 'k'), ('gj', 'g'),
    ('ž', 'z'), ('š', 's'), ('č', 'c'), ('ć', 'k'), ('đ', 'g'), ('ǵ', 'g'), ('ḱ', 'k'),
]
_FOLD_RE = re.compile('|'.join(re.escape(a) for a, _ in _FOLD))
_FOLD_MAP = dict(_FOLD)


def to_latin(text: str) -> str:
    """Cyrillic letters to Latin (lowercase input expected); other characters unchanged."""
    return ''.join(_CYR.get(ch, ch) for ch in text)


def fold_variants(text: str) -> str:
    """to_latin, then fold the digraph/diacritic spellings sellers mix."""
    return _FOLD_RE.sub(lambda m: _FOLD_MAP[m.group(0)], to_latin(text))
