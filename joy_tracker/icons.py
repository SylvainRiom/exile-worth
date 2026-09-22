"""Automatic currency recognition from the artwork advertised by poe.ninja."""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import cv2
import numpy as np

from .model import DATA

SAGA_FAMILY = frozenset(('medveds-saga', 'voranas-saga', 'uhtreds-saga',
                         'olroths-saga', 'aldurs-saga'))


def fetch_icons(items, directory=DATA / 'icons', progress=None):
    """Content-addressed local cache; a missing icon never prevents pricing."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    images, errors, sources = {}, [], {}
    for item_id, item in items.items():
        source = item.get('image') or item.get('icon')
        if not source:
            errors.append(item_id)
            continue
        url = urljoin('https://web.poecdn.com', source)
        if urlparse(url).scheme != 'https':
            errors.append(item_id)
            continue
        sources.setdefault(url, []).append(item_id)

    def load(url):
        file = directory / (hashlib.sha256(url.encode()).hexdigest() + '.png')
        try:
            if file.exists():
                encoded = file.read_bytes()
            else:
                request = Request(url, headers={'User-Agent': 'ExileWorth/0.2 (local currency reader)'})
                with urlopen(request, timeout=8) as response:
                    encoded = response.read(2_000_001)
                if len(encoded) > 2_000_000:
                    raise ValueError('Icon too large')
            image = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_UNCHANGED)
            if image is None or image.ndim != 3 or image.shape[2] not in (3, 4):
                raise ValueError('Invalid icon')
            if not file.exists():
                file.write_bytes(encoded)
            return image
        except (OSError, ValueError, cv2.error):
            return None

    # Shared artwork is downloaded once; unavailable URLs cannot serialize all
    # downloads into several minutes of waiting.
    done = len(errors)
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(load, url): aliases for url, aliases in sources.items()}
        for future in as_completed(pending):
            aliases = pending[future]
            image = future.result()
            if image is None:
                errors.extend(aliases)
            else:
                images.update((item_id, image) for item_id in aliases)
            done += len(aliases)
            if progress:
                progress(done, len(items))
    # Stable order keeps shared-asset families deterministic across downloads.
    images = {item_id: images[item_id] for item_id in items if item_id in images}
    return images, errors


@dataclass(frozen=True)
class IconMatch:
    item: str | None
    confidence: float
    candidate: str | None = None
    margin: float = 0
    alternatives: tuple[str, ...] = ()


class IconMatcher:
    """Masked colour correlation over several icon scales and alignments.

    Stack counters are excluded. Lower-right variant marks remain and receive
    extra weight. The runner-up is a *different currency*, not another scale.
    """
    def __init__(self, images, threshold=.92, margin=.015):
        self.threshold, self.margin = threshold, margin
        self.ids, templates, masks = [], [], []
        unique = {}
        for item, source in images.items():
            digest = hashlib.sha256(source.tobytes() + str(source.shape).encode()).hexdigest()
            if digest not in unique:
                unique[digest] = [source, []]
            unique[digest][1].append(item)
        self.aliases = {}
        for source, aliases in unique.values():
            item = aliases[0]
            self.aliases[item] = tuple(aliases)
            if source.shape[2] == 3:
                # Opaque artwork still works, but transparent CDN assets are preferred.
                source = np.dstack((source, np.full(source.shape[:2], 255, np.uint8)))
            for size in (44, 48, 52, 56, 60):
                scaled = cv2.resize(source, (size, size), interpolation=cv2.INTER_AREA)
                for dx in (-4, -2, 0, 2, 4):
                    for dy in (-4, -2, 0, 2, 4):
                        # Keep the original fine grid, plus a wider coarse grid.
                        # Expedition artwork can sit off-centre inside its frame.
                        if (abs(dx) == 4 and abs(dy) == 2) or (abs(dy) == 4 and abs(dx) == 2):
                            continue
                        canvas = np.zeros((51,52,4), np.uint8)
                        x, y = (52-size)//2+dx, (51-size)//2+dy
                        x1,y1,x2,y2 = max(0,x),max(0,y),min(52,x+size),min(51,y+size)
                        canvas[y1:y2,x1:x2] = scaled[y1-y:y2-y,x1-x:x2-x]
                        small = cv2.resize(canvas, (26,26), interpolation=cv2.INTER_AREA).astype(np.float32)
                        weight = (small[:,:,3] / 255) ** 2
                        weight[:10] = 0  # white stack quantity, read separately
                        if len(aliases) > 1:
                            # These CDN images omit the tier added by the game.
                            weight[17:,17:] = 0
                        if weight.sum() < 25:
                            continue
                        masks.append(np.repeat(weight[:,:,None], 3, axis=2).ravel())
                        templates.append((small[:,:,:3] / 255).ravel())
                        self.ids.append(item)
        self.ids = np.array(self.ids)
        self.weights = np.asarray(masks, np.float32)
        raw = np.asarray(templates, np.float32)
        self.templates = raw * self.weights if len(raw) else raw
        self.energy = (raw * self.templates).sum(axis=1) if len(raw) else np.array([])
        self.groups = {item: np.flatnonzero(self.ids == item) for item in self.aliases}

    def match_many(self, cells):
        if not len(self.ids):
            return [IconMatch(None, 0) for _ in cells]
        observed = np.array([cv2.resize(cell, (26,26), interpolation=cv2.INTER_AREA).ravel()
                             for cell in cells], dtype=np.float32) / 255
        dot = observed @ self.templates.T
        energy = (observed * observed) @ self.weights.T
        cosine = dot / np.sqrt(np.maximum(energy * self.energy, 1e-10))
        gain = dot / np.maximum(self.energy, 1e-10)
        # Empty dark silhouettes can correlate well but cannot have full icon brightness.
        cosine[(gain < .5) | (gain > 1.7)] = 0
        keys = [key for key,indices in self.groups.items() if len(indices)]
        scores = np.column_stack([cosine[:,self.groups[key]].max(axis=1) for key in keys])
        result = []
        for row in scores:
            order = np.argsort(row)[::-1]
            best = float(row[order[0]])
            gap = best - float(row[order[1]]) if len(order) > 1 else best
            candidate = keys[order[0]]
            accepted = best >= self.threshold and gap >= self.margin
            alternatives = self.aliases[candidate] if accepted else ()
            if not accepted and best >= self.threshold:
                # Preserve close, credible contenders as ambiguity. The scanner
                # may resolve documented fixed-slot families; never pick one here.
                alternatives = tuple(alias for index in order
                                     if row[index] >= max(self.threshold, best-self.margin)
                                     for alias in self.aliases[keys[index]])
                if len(alternatives) < 2 or not set(alternatives) <= SAGA_FAMILY:
                    alternatives = ()
            result.append(IconMatch(alternatives[0] if len(alternatives) == 1 else None,
                                    best, candidate, gap, alternatives))
        return result
