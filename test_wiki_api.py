import requests, json

# Test 1: action API with intro only
r = requests.get('https://en.wikipedia.org/w/api.php', 
    params={'action':'query','prop':'extracts','exintro':'1','explaintext':'1','titles':'Musee Marc Chagall','format':'json'}, 
    headers={'User-Agent':'Audioura/2.2'}, timeout=8)
data = r.json()
pages = data.get('query',{}).get('pages',{})
for pid, pd in pages.items():
    ext = pd.get('extract','')
    print(f'Test 1 (exintro): Page {pid}, extract_len={len(ext)}')
    if ext: print(f'  {ext[:300]}')

# Test 2: Marc Chagall (artist) — much richer
r2 = requests.get('https://en.wikipedia.org/w/api.php', 
    params={'action':'query','prop':'extracts','explaintext':'1','titles':'Marc Chagall','format':'json','exchars':'5000'}, 
    headers={'User-Agent':'Audioura/2.2'}, timeout=8)
data2 = r2.json()
pages2 = data2.get('query',{}).get('pages',{})
for pid, pd in pages2.items():
    ext = pd.get('extract','')
    print(f'\nTest 2 (Marc Chagall full): extract_len={len(ext)}')
    lower = ext.lower()
    for term in ['song of songs', 'sacrifice', 'biblical message', 'creation', 'exodus', 'nice']:
        print(f'  {term}: {term in lower}')
