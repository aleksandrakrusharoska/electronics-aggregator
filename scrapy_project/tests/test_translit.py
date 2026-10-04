from agents.clustering_agent import _normalise
from agents.dedup_agent import normalize_title
from agents.translit import fold_variants, to_latin


def test_to_latin_uses_the_standard_macedonian_spelling():
    assert to_latin('самсунг галакси') == 'samsung galaksi'
    assert to_latin('жица шарен чадор ќелија ѓубре џеб') == 'zhica sharen chador kjelija gjubre dzheb'
    assert to_latin('iphone 13 pro') == 'iphone 13 pro'          # Latin passes through


def test_fold_variants_merges_the_spellings_sellers_mix():
    spellings = ['зачуван', 'zachuvan', 'zacuvan', 'začuvan']
    assert {fold_variants(s) for s in spellings} == {'zacuvan'}


def test_dedup_titles_in_either_script_normalize_to_the_same_text():
    assert normalize_title('Самсунг Галакси С21 зачуван') == normalize_title('Samsung Galaksi S21 zacuvan')


def test_cluster_text_is_latin_and_keeps_readable_spelling():
    assert _normalise('Полнач за Самсунг') == 'polnach za samsung'
