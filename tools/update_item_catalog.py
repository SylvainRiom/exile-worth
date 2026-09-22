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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, help='Use a previously downloaded Expedition page')
    args = parser.parse_args()
    source = 'https://poe2db.tw/us/Economy_Expedition'
    if args.html:
        html = args.html.read_text('utf-8')
    else:
        request = Request(source, headers={'User-Agent': 'ExileWorth/0.2 (catalogue maintenance)'})
        with urlopen(request, timeout=15) as response:
            html = response.read(2_000_001).decode('utf-8')
    catalogue = CatalogueParser(source, 'Expedition')
    catalogue.feed(html)
    if len(catalogue.items) < 30 or 'verisium' not in catalogue.items:
        raise ValueError('Incomplete or changed source page; existing catalogue left intact')
    target = Path(__file__).resolve().parents[1] / 'joy_tracker' / 'item_catalog.json'
    data = {'checked': date.today().isoformat(), 'source': source,
            'items': sorted(catalogue.items.values(), key=lambda item: item['id'])}
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'{len(data["items"])} visual references saved; no prices imported')


if __name__ == '__main__':
    main()
