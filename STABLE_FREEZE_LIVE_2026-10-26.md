# Stable live state at the storied freeze (D724)

Recorded by GCloud_Storied, 2026-10-26 21:18 EDT, read-only from Cloud Run (project audiotours-migration, us-central1).
Freeze tag: `storied-freeze-2026-10-26` (origin/storied 202030e2). This file records what actually SERVES api.audioura.com, so a rollback can target exact revisions and digests.

Code behind the images: `audioura-storied:v6` = storied `17b341fe` (release v2t4); `audioura-storied:v8` (generator, by digest) = storied `3122cd71` (LOCAL-771); `audioura-storied:v4` = `d25454a` (v2t2); translation `v36-storied`; Beta-shared images `audioura:v3/v39/v41` and `api-gateway:v36` are unchanged Beta builds.

| service | serving revision (100%) | image as deployed | image digest |
|---|---|---|---|
| `api-gateway-storied` | `api-gateway-storied-00003-5zp` | `us-central1-docker.pkg.dev/audiotours-migration/services/api-gateway:v36` | `us-central1-docker.pkg.dev/audiotours-migration/services/api-gateway@sha256:71c5b90215c0c9db90555ab6870511dd9d07eb4bc2d96f180853763a35db4295` |
| `map-delivery` | `map-delivery-00016-tc2` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v6` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied@sha256:c2331fcab673b57573a9b2f92c322ae9a99118df8fb4532a18ebecec6f8934bd` |
| `newsletter-processor` | `newsletter-processor-00012-gxg` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v39` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura@sha256:34738e15575a7b96bae8e12129c28ef89199ed7a41cd7e31df4ff3870c289e5b` |
| `news-orchestrator` | `news-orchestrator-00023-bf6` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v41` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura@sha256:3167ba7833cde1d9892fb85f3c52e35ac99bac124abf8407fde740316d875edd` |
| `tour-orchestrator-storied` | `tour-orchestrator-storied-00009-65h` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v6` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied@sha256:c2331fcab673b57573a9b2f92c322ae9a99118df8fb4532a18ebecec6f8934bd` |
| `translation-service` | `translation-service-00022-72q` | `us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v36-storied` | `us-central1-docker.pkg.dev/audiotours-migration/services/translation-service@sha256:8ec2a7128b5c7284b3b6b6e70a9318a134063135f5f6a37c0eae5263ed8f472a` |
| `polly-tts` | `polly-tts-00007-bnd` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v3` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura@sha256:6dca0ba7421e3de019b7cc369d3ffffdd92e83575ad05d465d68edf2231b0774` |
| `tour-editing` | `tour-editing-00005-2xh` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v6` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied@sha256:c2331fcab673b57573a9b2f92c322ae9a99118df8fb4532a18ebecec6f8934bd` |
| `tour-generator-storied` | `tour-generator-storied-00010-ldx` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied@sha256:2d3519b8d083ed5bb91f29b06438fb3b2f98151492f6633f4971f530cea77963` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied@sha256:2d3519b8d083ed5bb91f29b06438fb3b2f98151492f6633f4971f530cea77963` |
| `tour-modernized-storied` | `tour-modernized-storied-00004-ssx` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v4` | `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied@sha256:54db0013d490bdcf872f227df60a5d084de891e9156eb8e111e3b4df3717778c` |

Notes:
- A `coordinates` URL is referenced in a Stable service env, but no Cloud Run service of that name exists.
- Roll back one service: `gcloud run services update-traffic <svc> --to-revisions=<rev>=100 --region us-central1 --project audiotours-migration`.
- Host routing: `api.audioura.com` and `storied-api.audioura.com` → `storied-matcher` on `audioura-url-map`; rollback to Beta: `gcloud compute url-maps remove-host-rule audioura-url-map --host=api.audioura.com`.
