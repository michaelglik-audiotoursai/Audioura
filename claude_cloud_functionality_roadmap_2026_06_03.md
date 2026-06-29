# Path to Full Cloud Functionality — What's Testable Now vs. What's Left

**Date:** 2026-06-03
**Context:** R2 secrets are fixed. Question: when can the *full* app — including generating tours and newsletters — be tested on cloud (off-WiFi)?

---

## TL;DR
- **On local WiFi: everything already works today** — generation, newsletters, tours — unchanged. Nothing here affects that.
- **On cloud/cellular, available now:** downloading & playing **existing** tours (once map-delivery picks up the new R2 secret — Kiro needs to force a new revision).
- **On cloud/cellular, NOT yet:** generating tours, generating newsletters, news, translation. These are blocked by remaining service deployments **and** one structural item: the mobile app can currently reach only **one** cloud service at a time. Full cloud generation needs the gateway (or per-service host support) first.

---

## 1. What you can test on cloud right now
**Existing-tour download/play over cellular.** R2 creds are set; once Kiro forces a new map-delivery revision so the service loads the new secret, set About → Cloud, paste the map-delivery URL, leave "gateway path routing" unchecked, go off-WiFi, and open an existing tour. This path is code-complete and verified (map-delivery + R2 dual-read). Works on both Android and iPhone.

## 2. The structural blocker for everything else — the mobile app reaches only ONE cloud service
In interim cloud mode the app uses a **single** `cloud_base_url` with prefixes off, so **every** service resolves to that **same** host. That's fine for the map-delivery-only download test, but a single tour-generation request touches **orchestrator → generator → modernized → translation → map-delivery** in one flow, and a newsletter touches the **newsletter/news** services. You can't point one base URL at all of them, and you can't swap it mid-flow.

So full cloud generation requires one of:
- **(Recommended) A single-domain gateway** (`api.audioura.com` or a GCP HTTPS Load Balancer) that path-routes `/orchestrator`, `/map-delivery`, `/newsletter`, … to each service **and strips the prefix**. Then you set `cloud_base_url` to the gateway, flip the app's **"gateway path routing" checkbox ON**, and all services are reachable through one domain — exactly what the v2.1.1 design was built for. No app rebuild.
- **(Alternative) Per-service host fields** in the app — more UI, and clunkier than the gateway.

Until the gateway exists, cloud testing is limited to the single-service download path.

## 3. Services still to deploy (from Phase E's own list)
| Service | Needed for | Status |
|---|---|---|
| translation-service | Multi-language tours (your RU/KO generations) | **Not deployed — HIGH** |
| coordinates | POI geo lookups during tour generation | Not deployed |
| news-orchestrator / news-generator / news-processor | News article generation | Not deployed |
| newsletter-processor | Newsletter crawling/processing | Not deployed |
| user-api (`:5003`) | Tour-status updates (currently raw SQL) | Not deployed — **see §4** |
| tour-editing | Custom tour editing | Not deployed |

(Deployed already: orchestrator, generator, modernized, map-delivery, polly-tts.)

## 4. The tour-status-update debt blocks cloud generation specifically
The app reports generation progress by issuing **raw SQL** via `DirectDbUpdate` to the `:5003` user-api service. That service isn't deployed, and it **shouldn't** be exposed publicly with a SQL endpoint. So even with the generation pipeline up, the status flow won't complete on cloud until this is **replaced with a proper REST status endpoint** on the orchestrator (the right fix), or user-api is deployed behind auth (worse). This is a shared-Dart + Services change, and it gates cloud tour generation.

## 5. Supporting data + security still pending
- **Cloud SQL data import:** small tables, `article_requests`, `news_audios`, and `custom_tours` aren't fully imported yet (the news FK ordering issue). Newsletters/news/custom-tours need these.
- **Cloud SQL lockdown:** still public IP; move to private IP + VPC connector before this is more than a short attended test. Not a functional blocker, but shouldn't slip.

---

## 6. Dependency-ordered path to "full cloud test"
Roughly in order (several can run in parallel):

1. **Now:** Kiro forces the map-delivery revision → you test existing-tour download over cellular. ✅ closes the first milestone.
2. **Deploy the generation siblings:** translation-service + coordinates, and set `TRANSLATION_URL` / `COORDINATES_URL` on the orchestrator. (polly-tts already done.)
3. **Replace the raw-SQL status update with a REST endpoint** (§4) so generation completes its status flow on cloud.
4. **Stand up the gateway** (single domain, path-route + strip) so the app can reach all services via one `cloud_base_url` with prefixes ON (§2). This is the unlock for end-to-end cloud generation from the phone.
5. **Finish the Cloud SQL data import** (small tables → article_requests → news_audios → custom_tours) for newsletters/news/custom tours.
6. **Deploy the news/newsletter services** (news-orchestrator/generator/processor, newsletter-processor) → cloud newsletter generation becomes testable.
7. **Lock down Cloud SQL** (VPC connector) before broad/unattended use.

**Result:** cloud **tour generation** becomes testable after steps 2-4 (+ relevant data). Cloud **newsletter generation** after steps 4-6. Until then, do generation/newsletter testing on **local WiFi** (fully working) and reserve cloud testing for the existing-tour download path.

---

## 7. Honest "when"
I won't put a date on it — that depends on Kiro's deploy velocity and how you choose to do the gateway. But the **sequence and dependencies are fixed**: the gateway (step 4) and the status-endpoint fix (step 3) are the two non-obvious gates, and the gateway is the single biggest unlock — without it the phone can't drive a multi-service cloud flow no matter how many services are deployed. If you want, I can write the spec for either the gateway (GCP HTTPS LB path matcher, or a tiny reverse-proxy service) or the orchestrator REST status endpoint, so those two critical-path items can start.
