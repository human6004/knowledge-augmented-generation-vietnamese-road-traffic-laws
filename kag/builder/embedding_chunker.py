"""Embedding-only offsets and deterministic overlap-aware vector aggregation."""
import math


CHUNKING_VERSION = 'boundary_offsets_v1'
BOUNDARIES = (('\n\n',), ('\n',), ('. ', '; ', ': '))


def _boundary(text, low, high, *, first=False):
    for separators in BOUNDARIES:
        candidates = []
        for separator in separators:
            pos = text.find(separator, max(0, low-len(separator)), high)
            while pos >= 0:
                end = pos + len(separator)
                if low <= end <= high:
                    candidates.append(end)
                pos = text.find(separator, pos+1, high)
        if candidates:
            return min(candidates) if first else max(candidates)
    return None


def chunk_text(text, max_chunk_chars=8000, overlap_chars=500):
    """Return contiguous source slices; no normalization, no text in metadata.

    Natural ends are chosen in the latter half of the window to avoid tiny
    chunks. Natural overlap starts stay within the requested maximum overlap.
    Unembeddable whitespace-only windows fail explicitly instead of disappearing.
    """
    if (not isinstance(text, str) or type(max_chunk_chars) is not int or max_chunk_chars < 1
            or type(overlap_chars) is not int or not 0 <= overlap_chars < max_chunk_chars):
        raise ValueError('positive chunk maximum and smaller nonnegative overlap required')
    if not text.strip():
        raise ValueError('no non-whitespace embedding content')
    offsets, start = [], 0
    while start < len(text):
        limit = min(start+max_chunk_chars, len(text))
        end = limit if limit == len(text) else (_boundary(text, start+max_chunk_chars//2, limit) or limit)
        if not text[start:end].strip():
            raise ValueError('whitespace-only window cannot be embedded within configured maximum')
        offsets.append((start,end))
        if end == len(text):
            break
        low = max(start+1, end-overlap_chars)
        start = (_boundary(text, low, end-1, first=True) or low) if overlap_chars else end
    return offsets


def split_chunk(text, offsets, min_chunk_chars=1000):
    """Bisect one failed source interval; children keep exact adjacent coverage."""
    start, end = offsets
    if type(min_chunk_chars) is not int or min_chunk_chars < 1 or not 0 <= start < end <= len(text):
        raise ValueError('valid source interval and positive minimum required')
    if end-start < 2*min_chunk_chars:
        return None
    middle = (start+end)//2
    low = max(start+min_chunk_chars, middle-(end-start)//4)
    high = min(end-min_chunk_chars, middle+(end-start)//4)
    cut = _boundary(text, low, high) or middle
    if not text[start:cut].strip() or not text[cut:end].strip():
        cut = middle
    if not text[start:cut].strip() or not text[cut:end].strip():
        return None
    return [(start,cut),(cut,end)]


def effective_weights(offsets, source_chars):
    """First covering chunk owns characters; later overlap gets zero extra weight.

    Intervals ordered by start must cover [0, source_chars] without gaps.
    Adaptive children wholly within an earlier overlap have weight zero.
    Splitting a failed interval never changes total source weight.
    """
    covered, previous_start, weights = 0, -1, []
    for start,end in offsets:
        if not 0 <= start <= covered or not start < end <= source_chars or start < previous_start:
            raise ValueError('chunk coverage gap or unordered interval')
        weights.append(max(0,end-covered))
        covered = max(covered,end)
        previous_start = start
    if covered != source_chars:
        raise ValueError('incomplete source coverage')
    return weights


def pool_vectors(vectors, weights, dimension):
    """Length-weighted mean followed by L2 normalization, scaled against overflow."""
    if (type(dimension) is not int or dimension < 1 or not vectors or len(vectors) != len(weights)
            or any(type(w) is not int or w < 0 for w in weights) or sum(weights) <= 0):
        raise ValueError('nonempty vectors and nonnegative weights with positive total required')
    if any(not isinstance(v, list) or len(v) != dimension or
           any(type(x) not in (int,float) or not math.isfinite(x) for x in v) or
           not any(x != 0 for x in v) for v in vectors):
        raise ValueError('invalid chunk vector')
    scale = max(abs(x) for w,v in zip(weights,vectors) if w > 0 for x in v)
    total = sum(weights)
    mean = [math.fsum((w/total)*(v[k]/scale) for w,v in zip(weights,vectors) if w > 0) for k in range(dimension)]
    norm = math.hypot(*mean)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError('aggregate vector has zero or invalid norm')
    return [x/norm for x in mean]
