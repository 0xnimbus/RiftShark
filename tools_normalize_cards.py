"""Normalize raw Riftcodex API dumps into data/cards/riftbound.json (one entry per functional card)."""
import json, re, sys, collections, html
raw = json.load(open(sys.argv[1]))
ICON = {':rb_might:': '[M]', ':rb_rune_rainbow:': '[A]', ':rb_exhaust:': '[T]', ':rb_rune_fury:': '[Fury]', ':rb_rune_body:': '[Body]',
        ':rb_rune_order:': '[Order]', ':rb_rune_calm:': '[Calm]', ':rb_rune_mind:': '[Mind]', ':rb_rune_chaos:': '[Chaos]'}
def clean(t):
    t = html.unescape(t or '')
    for k, v in ICON.items(): t = t.replace(k, v)
    t = re.sub(r':rb_energy_(\d+):', r'[\1]', t)
    t = re.sub(r':rb_[a-z_]+:', lambda m: '[' + m.group(0)[4:-1] + ']', t)
    t = re.sub(r'\(([^()]*?)\)', lambda m: '' if len(m.group(1)) > 25 and m.group(1)[0].isupper() else m.group(0), t)  # drop reminder text
    t = re.sub(r'\s+', ' ', t).strip()
    return t
KW = re.compile(r'\[(Accelerate|Action|Assault|Deathknell|Deflect|Ganking|Hidden|Legion|Reaction|Shield|Tank|Temporary|Vision|Equip|Mighty|Empower|Ambush|Repeat|Flow|Weaponmaster|Hunt|Backline|Unique)\]( ?(\d+))?')
cards = {}
order = []
for c in raw:
    md = c['metadata']
    if md['alternate_art'] or md['signature']: continue
    name = re.sub(r'\s*\((Overnumbered|Metal|Foil|Signature)\)\s*$', '', c['name'])
    plain = clean(c['text']['plain'])
    key = (name, plain)
    if key in cards:
        cards[key]['printings'].append(c['riftbound_id']); continue
    kws = {}
    for m in KW.finditer(plain):
        kws[m.group(1).lower()] = int(m.group(3)) if m.group(3) else True
    cards[key] = {
        'id': c['riftbound_id'].upper().rsplit('-', 1)[0] if c['riftbound_id'].count('-') == 2 else c['riftbound_id'].upper(),
        'name': name, 'type': c['classification']['type'].lower(), 'supertype': (c['classification']['supertype'] or '').lower() or None,
        'domains': [d.lower() for d in c['classification']['domain'] if d != 'Colorless'],
        'energy': c['attributes']['energy'], 'power': c['attributes']['power'] or 0, 'might': c['attributes']['might'],
        'tags': c['tags'], 'keywords': kws, 'text': plain, 'text_raw': html.unescape(c['text']['plain']),
        'set': c['set']['set_id'], 'rarity': c['classification']['rarity'], 'image': c['media']['image_url'],
        'printings': [c['riftbound_id']], 'script': None,
    }
    order.append(key)
out = [cards[k] for k in order]
# make ids unique
seen = collections.Counter(x['id'] for x in out)
dups = {k for k, v in seen.items() if v > 1}
for x in out:
    if x['id'] in dups: x['id'] = x['printings'][0].upper()
json.dump({'source': 'riftcodex.com API v0.2.0, fetched 2026-11-06', 'cards': out}, open(sys.argv[2], 'w'), indent=1)
print(len(out), 'cards;', collections.Counter(x['type'] for x in out))
