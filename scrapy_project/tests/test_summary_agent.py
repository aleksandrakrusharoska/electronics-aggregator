"""summary_agent: what gets stored from the model's key-info line (no LLM)."""
from types import SimpleNamespace

from agents import summary_agent as sa
from agents.parser_agent import latin_script

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


THINKCENTRE_DESC = ('Се продаваат 8 нови десктоп компјутери. Дел од компјутерите воопшто не се користени. '
                    'Преостаната гаранција 3 години. Компјутерите се продаваат со вклучен монитор (21.5")\n'
                    'CPU Type: Intel Core i3 Processor Intel Core i3-8100 Processor (6MB Cache, 3.60GHz) platformtype: SFF\n'
                    'Memory: 8GB DDR4 2666MHz UDIMM First Hard Drive: 256GB Solid State Drive, 2.5", SATA3, OPAL - Capable\n'
                    'Graphic Card: Integrated Graphic Card Onboard SATA Speakers: Internal Speaker Mouse: USB Calliope Mouse Black\n'
                    'Keyboard: USB Calliope KB BK EURO ENG Warranty: 5 Year Depot or Carry-in Ethernet: Integrated Ethernet')


def test_cyrillic_ad_with_an_english_spec_sheet_stays_cyrillic():
    assert not latin_script(THINKCENTRE_DESC)
    assert sa.clean_summary('Преостаната гаранција 3 години, вклучен монитор 21.5".', 'Lenovo ThinkCentre',
                            THINKCENTRE_DESC) == 'Преостаната гаранција 3 години, вклучен монитор 21.5".'


def test_latin_ad_with_core_i5_in_it_stays_latin():
    assert latin_script('Laptopot e kako nov, Intel Core i5, 8GB RAM, se prodava so polnac.')
    assert latin_script('Kupen od A1, sleduva kutija i polnac.')


def test_english_ad_counts_as_latin():
    assert latin_script('Nintendo Switch OLED with accessories, comes with the original Joy-Con controllers.')


def test_words_inside_a_link_do_not_decide_the_script():
    assert not latin_script('Линк од Плеј Стор: https://play.google.com/store/apps/details?id=mojavozacka.testovi_za_vozacka_dozvola '
                            'Офлајн верзија, во секое време, на секое место.')


class _FakeClients:
    """Answers with the given model outputs in turn, one per call."""

    def __init__(self, answers):
        self._clients = [(f'groq{i}', None) for i in range(4)]
        self._answers = iter(answers)

    def next(self):
        answer = next(self._answers)
        return 'groq', SimpleNamespace(invoke=lambda _m: SimpleNamespace(content=f'{{"notes": "{answer}"}}'))


def test_serbian_summary_is_retried_then_rejected():
    serbian = 'Korišten samo 2 meseci, dolazi so monitor i miš.'
    assert sa.summarise(_FakeClients([serbian, 'Koristen 2 meseci, so monitor.']), 'PC', LATIN_DESC, {}, None) == \
        'Koristen 2 meseci, so monitor.'
    assert sa.summarise(_FakeClients([serbian, serbian]), 'PC', LATIN_DESC, {}, None) is sa._REJECTED


def test_letters_the_seller_uses_are_not_serbian():
    desc = 'Prodavam laptop, odlično sočuvan, so polnač i torba. ' * 4
    assert not sa._serbian('Odlično sočuvan, so polnač i torba.', desc)
    assert sa._serbian('Odlicno socuvan, dolazi so torba.', desc)


def test_rejected_summary_keeps_the_old_notes(monkeypatch):
    parsed = SimpleNamespace(seller_notes='od parserot', specs={}, condition=None)
    clients = SimpleNamespace(_clients=[('groq', None)])
    monkeypatch.setattr(sa, 'summarise', lambda *a, **k: sa._REJECTED)
    sa.apply_summary(clients, 'Iphone 14', LATIN_DESC, parsed)
    assert parsed.seller_notes == 'od parserot'


def test_fixed_price_is_taken_out():
    assert sa.clean_summary('So site kabli i 30 igri; fiksna cena, bez zamena.', 'PS4', LATIN_DESC) == \
        'So site kabli i 30 igri, bez zamena.'
    assert sa.clean_summary('Со кутија и полнач, цената е фиксна.', 'Samsung S24', CYR_DESC) == 'Со кутија и полнач.'
    assert sa.clean_summary('Fiksna cena.', 'PS4', LATIN_DESC) is None


def test_summary_in_capitals_is_recased():
    assert sa.clean_summary('KUPEN OD A1, SLEDUVA KUTIJA.', 'Iphone 14', LATIN_DESC) == 'Kupen od a1, sleduva kutija.'


class _RateLimited(_FakeClients):
    """The first key answers with the given error, the rest with a summary."""

    def __init__(self, error):
        super().__init__(['Koristen 2 meseci, so monitor.'] * 4)
        self._error, self._calls, self._exhausted = error, 0, set()

    def next(self):
        self._calls += 1
        if self._calls == 1:
            def fail(_m):
                raise Exception(self._error)
            return 'groq0', SimpleNamespace(invoke=fail)
        return super().next()

    def mark_exhausted(self, name):
        self._exhausted.add(name)


def test_per_minute_limit_keeps_the_key():
    clients = _RateLimited('Error code: 429 - Rate limit reached on tokens per minute (TPM): Limit 8000')
    assert sa.summarise(clients, 'PC', LATIN_DESC, {}, None) == 'Koristen 2 meseci, so monitor.'
    assert clients._exhausted == set()


def test_daily_limit_takes_the_key_out():
    clients = _RateLimited('Error code: 429 - Rate limit reached on tokens per day (TPD): Limit 200000')
    assert sa.summarise(clients, 'PC', LATIN_DESC, {}, None) == 'Koristen 2 meseci, so monitor.'
    assert clients._exhausted == {'groq0'}
