"""Directly exercise _resolve_tour_from_db against the local R2+PG stand-ins."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Hard-set (not setdefault) so ambient/.env values for the REAL Cloudflare R2
# can never leak into this local test.
os.environ['DB_HOST'] = '127.0.0.1'
os.environ['DB_PORT'] = '5544'
os.environ['DB_NAME'] = 'audiotours'
os.environ['DB_USER'] = 'admin'
os.environ['DB_PASSWORD'] = 'password123'
os.environ['TOUR_STORAGE_MODE'] = 'cloud'
os.environ['BLOB_STORAGE_TYPE'] = 'r2'
os.environ['R2_ENDPOINT'] = 'http://127.0.0.1:9010'
os.environ['R2_BUCKET'] = 'v1-audiotours-r2-bucket'
os.environ['R2_ACCESS_KEY_ID'] = 'minioadmin'
os.environ['R2_SECRET_ACCESS_KEY'] = 'minioadmin'
os.environ['AWS_ACCESS_KEY_ID'] = 'dummy'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'dummy'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

import tour_editing_phase2 as t

print("STORAGE_MODE =", t.STORAGE_MODE)
storage = t._get_blob_storage()
print("blob storage =", storage)
if storage:
    print("R2 endpoint =", storage.endpoint, "bucket =", storage.bucket)
    try:
        data = storage.download('tours/1.zip')
        print("R2 direct download tours/1.zip OK bytes=", len(data))
    except Exception as e:
        print("R2 direct download FAILED:", repr(e))

p = t._resolve_tour_from_db('1')
print("resolve result =", p)
if p:
    import os as _os
    print("files:", _os.listdir(p))
