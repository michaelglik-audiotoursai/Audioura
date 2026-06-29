import requests, json, time, os, sys

api_key = os.environ.get('OPENAI_API_KEY')
if not api_key:
    print('ERROR: OPENAI_API_KEY not set')
    sys.exit(1)

poi_list = [
    'Stop 1: Biblical Message Room - 17 large-scale paintings, Old Testament scenes (1952-1966)',
    'Stop 2: The Tribe of Judah Room - Stained glass window 1964',
    'Stop 3: The Tribe of Naphtali Room - Stained glass windows',
    'Stop 4: Life and Death Room - Painting on mortality and transcendence',
    'Stop 5: Song of Songs Room - 5 paintings on the biblical love poem',
    'Stop 6: The Sacrifice of Isaac Room - Major painting of Abraham and Isaac',
    'Stop 7: The Prophet Room - Stained glass: Isaiah, Jeremiah, Ezekiel, Elijah',
    'Stop 8: The Seven Days of Creation Room - Large stained glass windows on Genesis',
    'Stop 9: The Tribe of Levi Room - Painting of the priestly tribe',
    'Stop 10: The Tribe of Benjamin Room - Painting 1964'
]

spine_prompt = """You are a master audio tour storyteller.

VENUE: Musee National Marc Chagall, Nice, France
TOUR TYPE: Museum (single building)
POIs:
""" + "\n".join(poi_list) + """

Create a narrative spine JSON with these exact fields:
- tour_hook: compelling opening mystery or question that gets answered by stop 10
- connecting_thread: one sentence — the single unifying theme across all 10 stops
- arc: array of exactly 10 objects, one per stop, each with:
    - stop: stop number (1-10)
    - name: stop name
    - chapter_role: one of "opening", "rising", "climax", "resolution"
    - emotional_beat: what the listener should FEEL at this stop (different for every stop)
    - unique_angle: one specific fact this stop reveals that NO other stop covers
    - plant: something to hint at for a later stop (or null)
    - callback: reference to a specific earlier stop by name (null for stop 1)
    - cliffhanger: one sentence tease that makes the listener want to walk to the next stop
- climax_stop: stop number where the emotional peak occurs
- resolution_stop: stop number of the final resolution
- closing_revelation: the insight at the final stop that reframes everything heard

Rules:
- Each stop must have a DIFFERENT emotional beat
- unique_angle must be factually grounded in real Chagall works or museum history
- The hook must be a genuine mystery about Chagall answered by the tour end
- Write for spoken audio — conversational, not academic
- Plants and callbacks must name the specific stop they reference
"""

headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + api_key}
data = {
    'model': 'gpt-4o',
    'messages': [
        {'role': 'system', 'content': 'You are a master storyteller. Return only valid JSON.'},
        {'role': 'user', 'content': spine_prompt}
    ],
    'temperature': 0.7,
    'max_tokens': 3000,
    'response_format': {'type': 'json_object'}
}

print('Calling gpt-4o for narrative spine...')
sys.stdout.flush()
t0 = time.time()
resp = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, data=json.dumps(data))
elapsed = time.time() - t0
result = resp.json()

if 'error' in result:
    print('ERROR:', result['error'])
    sys.exit(1)

tokens_in = result['usage']['prompt_tokens']
tokens_out = result['usage']['completion_tokens']
cost = (tokens_in * 0.0000025) + (tokens_out * 0.000010)
print('Time: %.1fs | Tokens: %d in / %d out | Cost: $%.5f' % (elapsed, tokens_in, tokens_out, cost))
sys.stdout.flush()

spine = json.loads(result['choices'][0]['message']['content'])
output = json.dumps(spine, indent=2, ensure_ascii=False)
print(output)
sys.stdout.flush()

with open('/app/tours/chagall_spine_poc.json', 'w', encoding='utf-8') as f:
    f.write(output)
print('Saved to /app/tours/chagall_spine_poc.json')
