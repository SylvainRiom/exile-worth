"""Refresh identification metadata only; never import PoE2DB economy prices.

Run: python tools/update_item_catalog.py
Review the JSON diff and add coverage before enabling a new stash category.
"""
import argparse
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class CatalogueParser(HTMLParser):
    def __init__(self, source, category):
        super().__init__()
        self.source, self.category = source, category
        self.items = {}
        self.current = None
        self.column = 0

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'tr':
            self.column = 0
        elif tag == 'td':
            self.column += 1
        elif tag == 'a':
            href = attributes.get('href', '')
            self.current = None
            if self.column == 1 and href.startswith('Economy_') and href[8:].islower():
                self.current = {'id': href[len('Economy_'):], 'name': '',
                                'category': self.category, 'source': self.source}
        elif tag == 'img' and self.current is not None:
            url = urljoin(self.source, attributes.get('src', ''))
            parsed = urlparse(url)
            if parsed.scheme == 'https' and parsed.hostname in ('web.poecdn.com', 'cdn.poe2db.tw'):
                self.current['image'] = url

    def handle_data(self, data):
        if self.current is not None:
            self.current['name'] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            item = self.current
            item['name'] = item['name'].strip()
            if item['name'] and item.get('image'):
                self.items[item['id']] = item
            self.current = None


# Every stash category whose items must be identifiable without prices. Each
# entry names the page, the least number of items expected and one item id that
# must be present: a page that changed shape leaves the catalogue untouched.
SOURCES = {
    'Expedition': ('https://poe2db.tw/us/Economy_Expedition', 30, 'verisium'),
    'Breach': ('https://poe2db.tw/us/Economy_Breach', 25, 'breach-splinter'),
    'Abyss': ('https://poe2db.tw/us/Economy_Abyss', 20, 'ancient-rib'),
    'Delirium': ('https://poe2db.tw/us/Economy_Delirium', 25, 'ancient-diluted-liquid-greed'),
    'Essences': ('https://poe2db.tw/us/Economy_Essences', 45, 'essence-of-battle'),
    'Ritual': ('https://poe2db.tw/us/Economy_Ritual', 25, 'omen-of-amelioration'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', action='append', default=[], metavar='CATEGORY=PATH',
                        help='Use a previously downloaded page for one category')
    args = parser.parse_args()
    pages = dict(entry.split('=', 1) for entry in args.html)
    items = {}
    for category, (source, minimum, sentinel) in SOURCES.items():
        if category in pages:
            html = Path(pages[category]).read_text('utf-8')
        else:
            request = Request(source, headers={'User-Agent': 'ExileWorth/0.2 (catalogue maintenance)'})
            with urlopen(request, timeout=15) as response:
                html = response.read(2_000_001).decode('utf-8')
        catalogue = CatalogueParser(source, category)
        catalogue.feed(html)
        if len(catalogue.items) < minimum or sentinel not in catalogue.items:
            raise ValueError(f'{category}: incomplete or changed source page; existing catalogue left intact')
        clashes = set(items) & set(catalogue.items)
        if clashes:
            raise ValueError(f'{category}: ids already taken by another category: {sorted(clashes)}')
        items.update(catalogue.items)
    target = Path(__file__).resolve().parents[1] / 'exile_worth' / 'item_catalog.json'
    # A reference verified earlier stays when the page stops listing it: an item
    # still sitting in someone's stash must remain identifiable.
    previous = json.loads(target.read_text('utf-8'))['items'] if target.exists() else []
    kept = [item for item in previous if item['id'] not in items]
    for item in kept:
        items[item['id']] = item
    if kept:
        print('kept, no longer listed by the source:', ', '.join(sorted(item['id'] for item in kept)))
    data = {'checked': date.today().isoformat(),
            'sources': {category: source for category, (source, _, _) in SOURCES.items()},
            'items': sorted(items.values(), key=lambda item: item['id'])}
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'{len(data["items"])} visual references saved; no prices imported')


if __name__ == '__main__':
    main()
