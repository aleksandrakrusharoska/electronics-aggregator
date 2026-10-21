"""resummarise_notes.short_fix: notes of ads with a short description (no LLM)."""
from resummarise_notes import short_fix

DESC = 'Samsung Galaxy S21 koristen kako nov, so kutija i polnac'


def test_notes_only_in_capitals_are_recased():
    assert short_fix('GARANCIJA 2 GODINI', DESC) == 'Garancija 2 godini'


def test_a_price_is_cleared_not_recased():
    assert short_fix('CENA 190 EVRA', DESC) is None
    assert short_fix('SAMO KOMPLET 7500DEN FIKSNO', DESC) is None
    assert short_fix('300 €', DESC) is None


def test_days_are_not_a_price():
    assert short_fix('KORISTEN 5 DENA', DESC) == 'Koristen 5 dena'


def test_contact_or_english_is_cleared():
    assert short_fix('ZA POVEKJE INFO 070 123 456', DESC) is None
    assert short_fix('includes cable and 5-month warranty', DESC) is None
