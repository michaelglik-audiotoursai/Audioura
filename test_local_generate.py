"""Quick test: fire a generate request at localhost:5000 and check status."""
import requests
import time

resp = requests.post('http://localhost:5000/generate', json={
    'location': 'Musee National Marc Chagall, Nice, France',
    'tour_type': 'museum',
    'total_stops': 10,
})
print(f"POST /generate: {resp.status_code}")
data = resp.json()
print(f"  job_id: {data.get('job_id')}")
print(f"  status: {data.get('status')}")

job_id = data.get('job_id', '')
if job_id:
    for i in range(6):
        time.sleep(5)
        status_resp = requests.get(f'http://localhost:5000/status/{job_id}')
        sdata = status_resp.json()
        s = sdata.get('status', '?')
        p = sdata.get('progress', '')[:80]
        print(f"  [{i*5+5}s] status={s} progress={p}")
        if s in ('completed', 'error'):
            if s == 'error':
                print(f"  ERROR: {sdata.get('error', '')}")
            break
