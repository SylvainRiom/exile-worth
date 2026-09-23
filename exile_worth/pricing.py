"""Cached economy access. No screenshot or inventory leaves this application."""
import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .model import DATA
from .catalog import with_reference_items


# poe.ninja split Expedition in September 2026: alloys, crests, Verisium and
# Starlit Ores moved to their own `Verisium` overview; `Expedition` keeps the
# sagas, fluxes and logbooks. Both are needed to price an Expedition tab.
STASH_CATEGORIES = ('Currency', 'Expedition', 'Verisium', 'Breach', 'Abyss', 'Delirium', 'Essences',
                    'Ritual', 'Runes', 'SoulCores', 'Idols')


class Ninja:
    def __init__(self, base='https://poe.ninja', contact='local-prototype', cache=None):
        self.base = base.rstrip('/')
        self.agent = f'ExileWorth/0.1 ({contact})'
        self.cache = cache or DATA / 'prices'
        self.cache.mkdir(parents=True, exist_ok=True)

    def get(self, route):
        file = self.cache / (hashlib.sha256((self.base + route).encode()).hexdigest() + '.json')
        cached = json.loads(file.read_text('utf-8')) if file.exists() else None
        if cached and time.time() - cached['checked'] < 3600:
            return cached
        headers = {'User-Agent': self.agent, 'Accept': 'application/json'}
        if cached and cached.get('etag'):
            headers['If-None-Match'] = cached['etag']
        try:
            with urlopen(Request(self.base + route, headers=headers), timeout=20) as response:
                result = dict(data=json.load(response), checked=time.time(), fetched=time.time(),
                              etag=response.headers.get('ETag'), stale=False)
        except HTTPError as exc:
            if exc.code == 304 and cached:
                result = dict(cached, checked=time.time(), stale=False)
            elif cached:
                return dict(cached, stale=True)
            else:
                raise
        except (OSError, ValueError):
            if cached:
                return dict(cached, stale=True)
            raise
        temporary = file.with_suffix('.tmp')
        temporary.write_text(json.dumps(result), encoding='utf-8')
        temporary.replace(file)
        return result

    def leagues(self):
        return self.get('/poe2/api/economy/leagues')['data']

    def currencies(self, league):
        return self.overview(league, 'Currency')

    def overview(self, league, category):
        result = self.get('/poe2/api/economy/exchange/current/overview?' +
                          urlencode({'league': league, 'type': category}))
        return parse_overview(result['data']) | {'fetched': result['fetched'], 'stale': result['stale']}

    def stash_market(self, league):
        # Independent categories can be fetched together without multiplying
        # the wait for an unavailable endpoint.
        with ThreadPoolExecutor(max_workers=len(STASH_CATEGORIES)) as pool:
            futures = {category: pool.submit(self.overview, league, category)
                       for category in STASH_CATEGORIES}
            results = {}
            unavailable = []
            for category, future in futures.items():
                try:
                    results[category] = future.result()
                except (OSError, ValueError, KeyError):
                    unavailable.append(category)
        base = results.pop('Currency', None)
        if base is None:
            base = next(iter(results.values()),
                        dict(items={}, prices={}, primary='?', fetched=time.time(), stale=True))
            if results:
                results.pop(next(iter(results)))
        for category, overview in results.items():
            base = merge_overviews(base, overview, category)
        return with_reference_items(dict(base, unavailable_categories=unavailable +
                                         base.get('unavailable_categories', [])))


def merge_overviews(currency, expedition, category='Expedition'):
    """Keep common reference rates from Currency; convert category prices if needed."""
    factor = 1 if expedition['primary'] == currency['primary'] else currency['prices'].get(expedition['primary'])
    items = dict(currency['items'])
    prices = dict(currency['prices'])
    for item, metadata in expedition['items'].items():
        if item in items:
            continue
        items[item] = metadata
        if factor is not None and item in expedition['prices']:
            prices[item] = expedition['prices'][item]*factor
    return dict(currency,items=items,prices=prices,
                fetched=min(currency['fetched'],expedition['fetched']),
                stale=currency['stale'] or expedition['stale'],
                unavailable_categories=currency.get('unavailable_categories', []) +
                                       ([] if factor is not None else [category]))


def parse_overview(data):
    core = data['core']
    primary = core['primary']
    if isinstance(primary, dict):
        primary = primary['id']
    items = {str(item['id']): item for item in [*core['items'], *data.get('items', [])]}
    prices = {}
    for line in data['lines']:
        value = line.get('primaryValue')
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
            prices[str(line['id'])] = value
    prices[str(primary)] = 1.0
    return {'items': items, 'prices': prices, 'primary': str(primary)}
