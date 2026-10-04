from ads_scraper.normalize import normalize_pazar3_condition


def test_pazar3_dropdown_values_map_to_canonical_conditions():
    assert normalize_pazar3_condition('Ново') == 'New'
    assert normalize_pazar3_condition('Користено - Како Ново') == 'Used - Like New'
    assert normalize_pazar3_condition('Користено - Во добра состојба') == 'Used - Good'
    assert normalize_pazar3_condition('Користено - Во солидна состојба') == 'Used - Fair'


def test_spacing_and_case_do_not_matter():
    assert normalize_pazar3_condition('  користено  -  во солидна   состојба ') == 'Used - Fair'


def test_unknown_values_pass_through_for_the_llm_parser():
    assert normalize_pazar3_condition('исправна состојба') == 'исправна состојба'
    assert normalize_pazar3_condition(None) is None
    assert normalize_pazar3_condition('') == ''
