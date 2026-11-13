MAX_SECONDS = 60  # the encoder reads 256 word pieces; 60 s fits
MAX_WORDS = 180


def _too_big(lines):
    seconds = max(line.start + line.duration for line in lines) - lines[0].start  # captions can overlap
    words = sum(len(line.text.split()) for line in lines)
    return seconds > MAX_SECONDS or words > MAX_WORDS


def cut_parts(fetched):  # caption lines -> (start, end, text) parts, never splitting a line
    parts, current = [], []
    for line in sorted(fetched, key=lambda line: line.start):
        if current and _too_big(current + [line]):
            parts.append(current)
            current = []
        current.append(line)
    if current:
        parts.append(current)
    return [(p[0].start, max(line.start + line.duration for line in p), ' '.join(line.text for line in p)) for p in parts]
