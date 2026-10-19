"""summary_agent: what gets stored from the model's key-info line (no LLM)."""
from types import SimpleNamespace

from agents import summary_agent as sa

LATIN_DESC = 'Prodavam Iphone 14 128gb, kupen od A1, sleduva kutija i polnac. ' * 4
CYR_DESC = 'Се продава Samsung S24, купен од T-home со уште 1 година гаранција. ' * 4


def test_short_descriptions_are_left_to_the_parser():
    assert not sa.needs_summary('kratok opis')
    assert sa.needs_summary(LATIN_DESC)


def test_cyrillic_words_in_a_latin_ad_are_transliterated():
    assert sa.clean_summary('Kupen od A1, sleduva кутија i polnac.', 'Iphone 14', LATIN_DESC) == \
        'Kupen od A1, sleduva kutija i polnac.'


def test_cyrillic_ad_keeps_cyrillic():
    assert sa.clean_summary('Купен од T-home, гаранција 1 година.', 'Samsung S24', CYR_DESC) == \
        'Купен од T-home, гаранција 1 година.'


def test_dashes_and_special_spaces_are_normalised():
    assert sa.clean_summary('Garancija 1‑godishna – kutija', 'Iphone', LATIN_DESC) == \
        'Garancija 1-godishna , kutija'


def test_contact_too_long_or_title_only_is_dropped():
    assert sa.clean_summary('Javete se na 070 123 456', 'Iphone 14', LATIN_DESC) is None
    assert sa.clean_summary('x' * 200, 'Iphone 14', LATIN_DESC) is None
    assert sa.clean_summary('Iphone 14 128gb', 'Iphone 14 128gb', LATIN_DESC) is None
    assert sa.clean_summary(None, 'Iphone 14', LATIN_DESC) is None


def test_english_summary_of_a_macedonian_ad_is_dropped():
    assert sa.clean_summary('Original box and charger included', 'Iphone 14', LATIN_DESC) is None


def test_failed_call_keeps_the_parser_notes(monkeypatch):
    parsed = SimpleNamespace(seller_notes='od parserot', specs={}, condition=None)
    clients = SimpleNamespace(_clients=[('groq', None)])
    monkeypatch.setattr(sa, 'summarise', lambda *a, **k: sa._UNSET)
    sa.apply_summary(clients, 'Iphone 14', LATIN_DESC, parsed)
    assert parsed.seller_notes == 'od parserot'


def test_null_summary_clears_the_notes(monkeypatch):
    parsed = SimpleNamespace(seller_notes='od parserot', specs={}, condition=None)
    clients = SimpleNamespace(_clients=[('groq', None)])
    monkeypatch.setattr(sa, 'summarise', lambda *a, **k: None)
    sa.apply_summary(clients, 'Iphone 14', LATIN_DESC, parsed)
    assert parsed.seller_notes is None
