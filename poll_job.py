import requests, time, sys
job_id = sys.argv[1] if len(sys.argv) > 1 else 'd6c05532-ccc6-49a9-a583-ae9edf9188cc'
for i in range(30):
    time.sleep(5)
    r = requests.get(f'http://localhost:5000/status/{job_id}').json()
    s = r.get('status', '?')
    p = r.get('progress', '')[:60]
    print(f'[{(i+1)*5}s] {s}: {p}')
    if s == 'completed':
        print(f'  OUTPUT: {r.get("output_file", "")}')
        break
    if s == 'error':
        err = r.get('error', '')
        print(f'  ERROR: {err}')
        break
