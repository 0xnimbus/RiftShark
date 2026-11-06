"""Build data/cards/riftbound.json from the official card gallery (primary) plus the Riftcodex API dump (promos only).

usage: python tools_normalize_cards.py gallery_next.json all_cards_raw.json data/cards/riftbound.json
"""
import json, re, sys, collections, html

ICON = {':rb_might:': '[M]', ':rb_rune_rainbow:': '[A]', ':rb_exhaust:': '[T]', ':rb_rune_fury:': '[Fury]', ':rb_rune_body:': '[Body]',
        ':rb_rune_order:': '[Order]', ':rb_rune_calm:': '[Calm]', ':rb_rune_mind:': '[Mind]', ':rb_rune_chaos:': '[Chaos]'}
KW = re.compile(r'\[(Accelerate|Action|Assault|Deathknell|Deflect|Ganking|Hidden|Legion|Reaction|Shield|Tank|Temporary|Vision|Equip|Mighty|Empower|Ambush|Repeat|Flow|Weaponmaster|Hunt|Backline|Unique|Disarm|Deploy|Quick-Draw|Show Off|Level)\]( ?(\d+))?')


def clean(t):
    t = html.unescape(t or '')
    t = re.sub(r'<br\s*/?>|</p>\s*<p>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    for k, v in ICON.items():
        t = t.replace(k, v)
    t = re.sub(r':rb_energy_(\d+):', r'[\1]', t)
    t = re.sub(r':rb_[a-z_]+:', lambda m: '[' + m.group(0)[4:-1] + ']', t)
    t = t.replace('[S]', '[M]')
    t = re.sub(r'\s*\(([^()]*?)\)', lambda m: '' if len(m.group(1)) > 25 and m.group(1)[0].isupper() else m.group(0), t)  # reminder text
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\s*\n\s*', '\n', t).strip()
    return t


def keywords(text):
    kws = {}
    for m in KW.finditer(text):
        k = m.group(1).lower().replace(' ', '_').replace('-', '_')
        kws[k] = int(m.group(3)) if m.group(3) else True
    return kws


def from_gallery(c):
    name = c['name'] + (', ' + c['subtitle'] if c.get('subtitle') else '')
    types = [t['id'] for t in c['cardType']['type']]
    incomplete = False
    if not types:  # a few gallery entries have no type; recover it from the accessibility text
        m = re.match(r'Riftbound (\w+):', c['cardImage'].get('accessibilityText', ''))
        if not m or m.group(1) not in ('Unit', 'Spell', 'Gear', 'Legend', 'Battlefield', 'Rune'):
            return None
        types = [m.group(1).lower()]
        incomplete = True
    sup = [t['id'] for t in c['cardType'].get('superType') or []]
    txt = clean(c['text']['richText']['body']) if c.get('text') else ''
    eff = clean(c['effect']['richText']['body']) if c.get('effect') else ''
    v = lambda k: (c.get(k) or {}).get('value', {}).get('id') if c.get(k) else None
    return {
        'id': c['publicCode'].split('/')[0].upper(), 'name': name, 'type': types[0], 'types': types,
        'supertype': sup[0] if sup else None,
        'domains': [d['id'] for d in c['domain']['values'] if d['id'] != 'colorless'],
        'energy': v('energy'), 'power': v('power') or 0, 'might': v('might'), 'might_bonus': v('mightBonus'),
        'tags': (c.get('tags') or {}).get('tags', []), 'keywords': keywords(txt + ' ' + eff),
        'text': txt, 'effect_text': eff, 'text_raw': html.unescape(c['text']['richText']['body']) if c.get('text') else '',
        'set': c['set']['value']['id'], 'rarity': c['rarity']['value']['id'], 'image': c['cardImage']['url'],
        'printings': [c['id']], 'source': 'official-gallery', 'script': None,
        'data_incomplete': incomplete or (not c['domain']['values'] and types[0] not in ('battlefield',)),
    }


def from_codex(c):
    txt = clean(c['text']['plain'])
    return {
        'id': c['riftbound_id'].upper().rsplit('-', 1)[0] if c['riftbound_id'].count('-') == 2 else c['riftbound_id'].upper(),
        'name': re.sub(r'\s*\((Overnumbered|Metal|Foil|Signature)\)\s*$', '', c['name']).replace(' - ', ', '),
        'type': c['classification']['type'].lower(), 'types': [c['classification']['type'].lower()],
        'supertype': (c['classification']['supertype'] or '').lower() or None,
        'domains': [d.lower() for d in c['classification']['domain'] if d != 'Colorless'],
        'energy': c['attributes']['energy'], 'power': c['attributes']['power'] or 0, 'might': c['attributes']['might'], 'might_bonus': None,
        'tags': c['tags'], 'keywords': keywords(txt), 'text': txt, 'effect_text': '', 'text_raw': html.unescape(c['text']['plain']),
        'set': c['set']['set_id'], 'rarity': c['classification']['rarity'].lower(), 'image': c['media']['image_url'],
        'printings': [c['riftbound_id']], 'source': 'riftcodex', 'script': None,
    }


def main(gallery_path, codex_path, out_path):
    g = json.load(open(gallery_path))
    items = g['props']['pageProps']['page']['blades'][2]['cards']['items']
    cards, order = {}, []
    rank = {'common': 0, 'uncommon': 1, 'rare': 2, 'epic': 3, 'showcase': 9, 'overnumbered': 9, 'signature': 9}
    for c in sorted(items, key=lambda c: (rank.get(c['rarity']['value']['id'], 5), c['collectorNumber'])):
        x = from_gallery(c)
        if x is None:
            continue
        key = (x['name'], x['text'], x['effect_text'])
        if key in cards:
            cards[key]['printings'].append(c['id'])
        else:
            cards[key] = x; order.append(key)
    known_printings = {p.lower() for x in cards.values() for p in x['printings']}
    norm = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
    by_name = {}
    for k, x in cards.items():
        by_name.setdefault((norm(x['name']), x['type']), k)
    added = 0
    for c in json.load(open(codex_path)):
        if c['riftbound_id'].lower() in known_printings:
            continue
        x = from_codex(c)
        k = by_name.get((norm(x['name']), x['type']))
        if k is not None:   # promo / alternate printing of a card the gallery already has
            cards[k]['printings'].append(c['riftbound_id'])
            continue
        if c['metadata']['alternate_art'] or c['metadata']['signature']:
            continue
        key = (x['name'], x['text'], '')
        if key in cards:
            cards[key]['printings'].append(c['riftbound_id']); continue
        cards[key] = x; order.append(key); added += 1
        by_name[(norm(x['name']), x['type'])] = key
    out = [cards[k] for k in order]
    import os
    ovp = os.path.join(os.path.dirname(out_path), 'overrides.json')
    if os.path.exists(ovp):
        ov = json.load(open(ovp))
        for x in out:
            if x['id'] in ov:
                x.update(ov[x['id']])
    seen = collections.Counter(x['id'] for x in out)
    for x in out:
        if seen[x['id']] > 1:
            x['id'] = x['printings'][0].upper()
    json.dump({'sources': 'playriftbound.com card gallery (primary) + riftcodex.com API (promos); fetched 2026-11-06', 'cards': out},
              open(out_path, 'w'), indent=1)
    print(len(out), 'cards;', added, 'from riftcodex only;', collections.Counter(x['type'] for x in out), collections.Counter(x['set'] for x in out))


if __name__ == '__main__':
    main(*sys.argv[1:4])
