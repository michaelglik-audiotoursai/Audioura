# tile_proxy — Deploy notes (GCloud_Storied) · LOCAL-854 / D757

Our own map-tile cache. The app points `MAP_TILE_URL` at this service; it serves
tiles from a Google Cloud Storage bucket and only reaches the tile origin on a
cache miss, serving a stale cached copy when the origin is unreachable. This
keeps us inside OSM's tile-usage policy and keeps the Home map alive on the
flaky networks (Vietnam) that greyed it before.

**Do NOT deploy from this document automatically.** These are the steps for a
human operator (LEAD / GCloud_Storied) to run once, reviewed. Nothing here is
executed by the LOCAL-854 change.

---

## What gets created

| Resource            | Value                                              |
|---------------------|----------------------------------------------------|
| Cloud Run service   | `tile-proxy-subscribed`                            |
| Region              | the GCloud_Storied region (e.g. `us-central1`)     |
| Scaling             | min instances **0**, max instances **3**           |
| Memory              | **256Mi**, CPU 1                                    |
| GCS bucket          | `audioura-tile-cache-subscribed` (90-day lifecycle)|
| Runtime SA          | `tile-proxy-subscribed@<project>.iam.gserviceaccount.com` |
| SA role             | `roles/storage.objectAdmin` **on that bucket only**|

The service is public (map tiles are public data); it holds no secret. If a
MapTiler key is introduced later it goes in a Secret, not in the image.

---

## 1. Bucket with a 90-day lifecycle

Tiles are a cache; expire them so the bucket does not grow without bound and so
we re-pull fresh tiles periodically.

```bash
PROJECT=<gcloud-storied-project>
REGION=us-central1
BUCKET=audioura-tile-cache-subscribed

gcloud storage buckets create "gs://$BUCKET" \
  --project="$PROJECT" --location="$REGION" \
  --uniform-bucket-level-access

cat > /tmp/lifecycle.json <<'JSON'
{ "rule": [ { "action": {"type": "Delete"}, "condition": {"age": 90} } ] }
JSON
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file=/tmp/lifecycle.json
```

## 2. Runtime service account, scoped to this bucket only

```bash
SA=tile-proxy-subscribed
gcloud iam service-accounts create "$SA" --project="$PROJECT" \
  --display-name="tile-proxy-subscribed runtime"

SA_EMAIL="$SA@$PROJECT.iam.gserviceaccount.com"

# objectAdmin on the ONE bucket (read + write cache objects). No project-wide role.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectAdmin"
```

## 3. Build and deploy

Build from this directory (`tile_proxy/` is its own build context).

```bash
IMAGE="$REGION-docker.pkg.dev/$PROJECT/containers/tile-proxy-subscribed:$(git rev-parse --short HEAD)"

gcloud builds submit --project="$PROJECT" --tag "$IMAGE" .

gcloud run deploy tile-proxy-subscribed \
  --project="$PROJECT" --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$SA_EMAIL" \
  --min-instances=0 --max-instances=3 \
  --memory=256Mi --cpu=1 \
  --concurrency=40 \
  --allow-unauthenticated \
  --set-env-vars=TILE_CACHE_BUCKET=$BUCKET,TILE_MAX_CONCURRENT_ORIGIN=4
```

`TILE_ORIGIN` is left at its default (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`).
The descriptive User-Agent is baked into the app.

## 4. Point the app at it

Rebuild the Flutter app with the deployed host (no code change — dart-define):

```bash
flutter build ipa --dart-define=MAP_TILE_URL=https://<cloud-run-host>/{z}/{x}/{y}.png
```

The app keeps direct OSM as the LAST fallback (see `lib/config/map_tiles.dart`)
and shows OSM attribution on every map.

## 5. Smoke test after deploy

```bash
HOST=https://<cloud-run-host>
curl -s "$HOST/health"                 # {"status":"ok",...}
curl -s -o /dev/null -w '%{http_code}\n' "$HOST/12/3262/1924.png"   # 200 (HCMC)
curl -s -o /dev/null -w '%{http_code}\n' "$HOST/20/1/1.png"         # 400 (z>19)
```

---

## Switching the origin to MapTiler later (no code change)

`TILE_ORIGIN` is a URL template with an optional `{key}`. To move off OSM:

```bash
gcloud run services update tile-proxy-subscribed --project="$PROJECT" --region="$REGION" \
  --set-env-vars=TILE_ORIGIN='https://api.maptiler.com/maps/streets/{z}/{x}/{y}.png?key={key}' \
  --update-secrets=TILE_ORIGIN_KEY=maptiler-key:latest
```

The key is read from the `TILE_ORIGIN_KEY` env/secret and injected into `{key}`.
It is never logged and never committed.

---

## Expected monthly cost (rough, order-of-magnitude)

Assumes a small subscribed field-test user base — a few thousand tile requests a
day, the vast majority served from cache after warm-up.

| Component                         | Basis                                  | Est. / month |
|-----------------------------------|----------------------------------------|--------------|
| Cloud Run (min 0, 256Mi)          | scales to zero; low request volume     | **$0–3**     |
| Cloud Storage storage             | tile cache, ~1–3 GB, 90-day expiry     | **< $0.10**  |
| Cloud Storage operations          | reads/writes at this volume            | **< $0.50**  |
| Egress                            | tiles are small PNGs, modest traffic   | **$0–2**     |
| **Total**                         |                                        | **≈ $1–5**   |

Cost is dominated by whether Cloud Run is kept warm. With `min-instances=0` it
scales to zero between sessions, so idle cost is essentially $0 and the figure
above is an active-use estimate. Caching makes origin pulls (and any future
MapTiler per-tile cost) a small fraction of total tile requests.
