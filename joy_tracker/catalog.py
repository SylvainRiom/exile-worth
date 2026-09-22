"""Versioned visual references, independent of league prices.

Names and image URLs come from PoE2DB / poe.ninja. Never attach a price to
these records: only the selected league's economy response can supply it.
"""
import json
from pathlib import Path


def reference_items():
    data = json.loads(Path(__file__).with_name('item_catalog.json').read_text('utf-8'))
    return {item['id']: item for item in data['items']}


def with_reference_items(market):
    items = reference_items()
    for item_id, metadata in market['items'].items():
        # Preserve the source reference but prefer current API metadata.
        reference = items.get(item_id, {})
        items[item_id] = dict(reference, **metadata)
        if not (metadata.get('image') or metadata.get('icon')) and reference.get('image'):
            items[item_id]['image'] = reference['image']
    return dict(market, items=items)
