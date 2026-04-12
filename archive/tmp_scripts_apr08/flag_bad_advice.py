import json, re
k = json.load(open('/root/Mining-Gaurdian/knowledge.json'))
issues = k.get('known_issues', [])

fleet_entries = [i for i in issues if i.get('miner_id') == 'fleet' and i.get('date') == '2026-04-07']
if not fleet_entries:
    print('No fleet synthesis found')
    exit()

fleet = fleet_entries[-1]
text = fleet.get('insight', '').lower()

bad_phrases = [
    'delta-t', 'delta t', 'hvac system', 'hvac capacity', 'cooling capacity',
    'overheat', 'thermal issue', 'thermal stress', 'temperature problem',
    'cooling margin', 'thermal margin', 'hvac headroom', 'hvac adequate',
    'cooling adequate', 'check the hvac', 'hvac check', 'thermal warning',
    'thermal headroom', 'supply temp', 'return temp', 'water temp',
    'minimal headroom', 'weather warm',
]

print('=' * 60)
print('SCANNING FLEET SYNTHESIS FOR FLAGGED ADVICE')
print('=' * 60)
hit_count = 0
for phrase in bad_phrases:
    count = text.count(phrase)
    if count > 0:
        hit_count += count
        idx = 0
        for _ in range(count):
            pos = text.find(phrase, idx)
            if pos == -1:
                break
            start = max(0, pos - 150)
            end = min(len(text), pos + len(phrase) + 150)
            context = text[start:end].replace('\n', ' ')
            print()
            print('FOUND: ' + phrase + ' at pos ' + str(pos))
            print('  ...' + context + '...')
            idx = pos + 1

print()
print('Total flagged hits:', hit_count)

temp_mentions = re.findall(r'(\d+(?:\.\d+)?)\s*(?:deg|c|celsius)', text)
print()
print('Temperature references:', sorted(set(temp_mentions)))
