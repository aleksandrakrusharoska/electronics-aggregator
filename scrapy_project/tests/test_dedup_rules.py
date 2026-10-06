from agents.dedup_agent import _phone_match, _seller_match, _titles_ok, normalize_title


def test_seller_names_match_across_scripts_and_spacing():
    assert _seller_match('Мартин', 'Martin')
    assert _seller_match('MobiRekord', 'Mobi Rekord')
    assert _seller_match('Dimitar', 'Dimitar Trajkovski')
    assert not _seller_match('Bujar', 'Dimitar')
    assert not _seller_match('------', '------')     # placeholder, not a name


def test_phone_numbers_compare_on_the_last_eight_digits():
    assert _phone_match('+389 70 426 811', '070426811')
    assert not _phone_match('070426811', '071261632')
    assert not _phone_match(None, None)


def test_different_models_from_one_shop_are_not_duplicates():
    ok = lambda a, b: _titles_ok(normalize_title(a), normalize_title(b))
    assert not ok('iPhone 16e 128GB - Socuvan kako nov 100%', 'iPhone 15 128GB - Socuvan kako nov 100%')
    assert not ok('iPhone 12 Mini 64GB - Socuvan kako nov', 'iPhone Xs Max 64GB - Socuvan kako nov')
    assert ok('iPhone 17 Pro 256GB - Socuvan kako nov', 'iPhone 17 Pro 256GB - Socuvan kako nov')
