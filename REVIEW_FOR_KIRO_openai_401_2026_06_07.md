# For Kiro Amazon-Q — Cloud OpenAI 401 (don't assume the key is revoked)

**Date:** 2026-06-07
**Scope:** Services/GCloud only.
**TL;DR:** ✅ Good news — the inter-service auth fix worked (the request now reaches `tour-generator`; no more 403). ❌ But the conclusion "the OpenAI key may be invalid/expired" is almost certainly **wrong**: the **same generation succeeded locally**, which proves a valid OpenAI key exists. So the cloud 401 is a **cloud key-delivery problem** (wrong/corrupted/stale value in Secret Manager, or the revision not reading it), **not** a revoked key. Don't go generate a new key first — verify the stored value.

---

## 1. The decisive evidence: local SUCCEEDED
Sir Michael ran the same request ("walking tour of Boston Common") **locally and it worked**, and **on cloud it failed**. Local generation calls OpenAI exactly like the cloud does. **If the OpenAI key were globally invalid/expired/revoked, local would fail too.** It didn't. Therefore a **valid OpenAI key exists and works** — the cloud just isn't sending that valid value.

So the question is **not** "is the key revoked?" — it's "**why does the cloud have a bad/wrong OpenAI key value?**"

(Also note the progress: the cloud request reached **PHASE 3A inside `tour-generator`**, which is the OpenAI call — meaning the previous **403 inter-service auth issue is resolved**. v7 worked. The 401 is the *next* layer down, inside the generator's OpenAI call.)

## 2. Most likely causes (cloud key delivery), in order
1. **The value in Secret Manager is wrong/corrupted/stale** — a truncated paste, an old/rotated key, or trailing whitespace (not necessarily `\r\n` — a single trailing space also 401s). The newline saga makes a mis-store very plausible.
2. **The generator revision isn't reading the updated secret.** Updating a Secret Manager value does **not** refresh a running Cloud Run revision unless it's bound to `:latest` **and a new revision is deployed/restarted**. If you updated the secret but didn't redeploy `tour-generator`, it's still serving the old (bad) value.
3. **Wrong secret/version bound** to the generator (e.g., bound to a specific old version, or a different secret).

🚩 **Red flag:** you mentioned the key "starting with `wpIWgo…`". Real OpenAI keys start with **`sk-`** (or `sk-proj-`). If the stored value's **prefix is not `sk-`**, it isn't a valid OpenAI key at all (truncated front, or the wrong secret entirely) — that alone explains the 401.

## 3. The one test that settles it
Pull the **exact** stored value and call OpenAI with it directly:
```bash
KEY="$(gcloud secrets versions access latest --secret=openai-api-key)"
printf '%s' "$KEY" | head -c 6   # should print: sk-...   (NOT wpIWgo)
curl -s -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/models \
  -H "Authorization: Bearer $KEY"
```
- **401** → the stored value is bad. Fix = re-store the **known-working local key** (the one that just succeeded locally), with **no newline/whitespace**, confirm it starts with `sk-` and matches the expected length, then **redeploy `tour-generator`**.
- **200** → the value is fine; the problem is the **service/binding** — confirm `tour-generator`'s live revision binds `openai-api-key:latest`, that the env var is actually set on that revision, and **redeploy** so it picks up the latest version.

## 4. Simplest fix (skip the guessing)
Take the OpenAI key that **works locally** (from the local `.env`/Docker env), store it in Secret Manager via the no-newline method (`[IO.File]::WriteAllText` → `--data-file`, or the GCP Console), verify `sk-` prefix + length + no trailing whitespace, then **redeploy `tour-generator`** (a new revision so it reads the update). Re-test the same Boston Common request. This sidesteps "is the cloud key revoked" entirely by using a value you already know is valid.

## 5. Why I'd push back on "check OpenAI dashboard / generate a new key"
Generating a brand-new key before confirming the stored value is the problem is premature, and it risks: (a) invalidating the key local dev relies on (if they share one), and (b) masking the real issue (a mis-stored secret / un-redeployed revision), which would recur with the new key too. Confirm the stored value with the §3 curl first; only generate a new key if that curl 401s **and** you also confirm the same value fails from your own machine (i.e., the key really is dead).

---

## Bottom line
The inter-service auth fix is confirmed working (403 gone). The cloud 401 is **not** evidence of a revoked key — **local success proves the key is valid.** It's a Secret-Manager/value/redeploy problem. Run the §3 curl on the exact stored value (check it starts with `sk-`), and if it 401s, re-store the **working local key** cleanly and **redeploy `tour-generator`**. Don't generate a new key until the stored value is ruled out.
