import json
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'zhenxia' / 'static'


class TranslationKeys(HTMLParser):
    def __init__(self):
        super().__init__()
        self.keys = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in {'data-i18n', 'data-i18n-placeholder', 'data-i18n-aria-label'}:
                self.keys.add(value)


def test_dictionaries_have_matching_keys_and_interpolation():
    import re

    zh = json.loads((STATIC / 'locales/zh-CN.json').read_text())
    en = json.loads((STATIC / 'locales/en.json').read_text())
    assert zh.keys() == en.keys()
    for key in zh:
        assert zh[key] and en[key]
        assert set(re.findall(r'\{\w+\}', zh[key])) == set(re.findall(r'\{\w+\}', en[key]))
    parser = TranslationKeys()
    parser.feed((STATIC / 'index.html').read_text())
    assert parser.keys <= zh.keys()
