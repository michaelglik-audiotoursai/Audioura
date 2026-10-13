# LOCAL-678 — Container meter audit (which images carry the network meter)

The network meter is installed in an image two lines in the Dockerfile:

    COPY _meter/ /opt/meter/
    ENV PYTHONPATH=/opt/meter

sitecustomize (in `_meter/`) then imports+installs `paid_api_meter` in every
Python process in the container. An image is a **blind spot** if it runs code
that calls a paid host (api.openai.com, generativelanguage.googleapis.com,
serper.dev) but does NOT have those two lines — or if a compose file overrides
`PYTHONPATH` to something other than `/opt/meter`.

## Images that HAVE the meter (metered) ✓
| Dockerfile | entrypoint | makes paid calls |
|---|---|---|
| Dockerfile.generator | generate_tour_text_service.py | yes (OpenAI, Gemini, Serper) |
| Dockerfile.orchestrator | tour_orchestrator_service.py | yes |
| Dockerfile.modernized | tour_generation_modernized.py | yes |
| Dockerfile.polly-tts | polly_tts_service.py | AWS Polly (metered boto3 path) |

The Mac's primary live generation stack (docker-compose-master.yml and
docker-compose.subscribed-local.yml → tour-generator, tour-orchestrator,
tour-generation-modernized-1, polly-tts-1) builds these four, and
subscribed-local also pins `PYTHONPATH=/opt/meter` in the compose env. So the
**main paid tour path on the Mac is metered**. The disposable `run_local*_live.sh`
A/B containers build `Dockerfile.generator`, so they are metered too.

## Blind-spot images — make paid calls, NO meter ✗
| Dockerfile | entrypoint | paid calls | where it runs |
|---|---|---|---|
| translation-service/Dockerfile | translation_service.py | OpenAI/Gemini translation | master (translation-service), subscribed-local (NOT given PYTHONPATH=/opt/meter) |
| Dockerfile.news-generator | news_generator_service.py | OpenAI | master (news-generator-1) |
| Dockerfile.news-orchestrator | news_orchestrator_service.py | OpenAI | master (news-orchestrator-1) |
| Dockerfile.news-processor | news_processor_service.py | OpenAI | master (news-processor-1) |
| Dockerfile.background-article-processor | background_article_processor_service.py | OpenAI | master (background-article-processor-1) |
| Dockerfile.simple-news-search | simple_news_search_service.py | Serper | master (simple-news-search-1) |
| Dockerfile.tour-processor | tour_generation_service.py | OpenAI/Gemini | docker-compose-complete / tour-processor composes |
| Dockerfile.cloudrun | per-CMD service selection | OpenAI/Gemini/Serper | docker-compose-beta-local (beta) and Cloud Run (GCloud) |
| Dockerfile (top-level) | varies | yes via generate_tour_text | docker-compose.dev.yml, master `translation-service` build:Dockerfile |

Note: …VCEA (the key with the Oct 11 spend) is the **Mac's** key; GCloud/laptop use …Nw8A.
So the Cloud Run cloudrun image is not the source of the Mac's unmetered …VCEA spend,
but it IS an unmetered image and is listed for completeness. The news stack and
translation-service DO run on the Mac and ARE plausible Mac blind spots.

## PYTHONPATH overrides that DISABLE the meter ✗
| compose file | service | override | effect |
|---|---|---|---|
| docker-compose-testing.yml:15 | testing | `PYTHONPATH=/app` | would mask /opt/meter — but Dockerfile.testing has no meter and runs `http.server` (no paid calls), so no live blind spot |

## Fix (not applied here — infra change, needs Michael's OK)
Add the two meter lines to each blind-spot Dockerfile that makes paid calls
(translation-service, the five news/newsletter images, tour-processor, cloudrun,
top-level Dockerfile), and give translation-service `PYTHONPATH=/opt/meter` in
docker-compose.subscribed-local.yml. The host-run blind spot is already closed by
`_meter/meter_bootstrap.py` (LOCAL-678 step 3). This file is the list requested by
the ticket's item 3.
