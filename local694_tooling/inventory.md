# LOCAL-694 — Subscribed app server-call inventory

Source: grep of `audio_tour_app/lib` for `Endpoints.get/post/url/base` + raw `http.`.
Service → port (local) and cloud path prefix from `lib/config/endpoints.dart`.

| # | Service (enum) | Method | Path | Screen / caller | Core flow? |
|---|---|---|---|---|---|
| 1 | orchestrator | POST | /generate-complete-tour | tour_generator_screen | generate (CORE) |
| 2 | orchestrator | GET | /status/{jobId} | tour_generator / background_service / background_tour_monitor | generate (CORE) |
| 3 | orchestrator | GET | /download/{jobId} | tour_generator / background_service / background_tour_monitor | generate/download (CORE) |
| 4 | orchestrator | GET | /health | about_screen | diagnostics |
| 5 | orchestrator | DELETE/GET | /delete-account/{userId} | about_screen | account |
| 6 | orchestrator | POST | /tour-status | tour_status_service | status |
| 7 | orchestrator | GET | /tour/{id}/unlock-state | tour_pricing_service | pricing |
| 8 | orchestrator | GET | /tour/{id}/price | tour_pricing_service | pricing |
| 9 | orchestrator | POST | /tour/{id}/price | tour_pricing_service | curator pricing |
| 10 | orchestrator | GET | /tour/{id}/sales | tour_pricing_service | curator pricing |
| 11 | orchestrator | GET | /price-tiers | tour_pricing_service | curator pricing |
| 12 | orchestrator | GET | /tour/{id}/reviews | tour_reviews_service | reviews |
| 13 | orchestrator | GET | /tour/{id}/distribution | tour_reviews_service | reviews |
| 14 | orchestrator | POST | /tour/{id}/review | tour_reviews_service | reviews |
| 15 | orchestrator | POST | /review/{id}/helpful | tour_reviews_service | reviews |
| 16 | orchestrator | POST | /review/{id}/reply | tour_reviews_service | reviews |
| 17 | orchestrator | POST | /tour/{id}/rating | tour_rating_service | ratings (CORE) |
| 18 | orchestrator | GET | /tour/{id}/rating | tour_rating_service | ratings (CORE) |
| 19 | orchestrator | GET | /wallet/{userId} | wallet_service | wallet |
| 20 | orchestrator | GET | /wallet/{userId}/transactions | wallet_service | wallet |
| 21 | orchestrator | GET | /plans/available | wallet_service | wallet |
| 22 | orchestrator | POST | /wallet/{userId}/topup | wallet_service | wallet |
| 23 | orchestrator | POST | /sync | outbox_service | sync |
| 24 | mapDelivery | GET | /tours-near/{lat}/{lng}?radius=.. | home_screen | map/tours-near (CORE) |
| 25 | mapDelivery | GET | /download-tour/{tourId} | home_screen / tour_generator / tour_translation_helper | download (CORE) |
| 26 | mapDelivery | GET | /search-tours?pattern=..&lat=..&lng=.. | home_screen | search (CORE) |
| 27 | mapDelivery | GET | /tour-by-code/{code} | home_screen | share code (CORE) |
| 28 | mapDelivery | GET | /tour/{id}/preview-audio | tour_preview_player | preview |
| 29 | mapDelivery | GET | /tour/{id}/score-explanation | score_explanation_service | score |
| 30 | mapDelivery | POST | /tour/{id}/rescore-request | score_explanation_service | score |
| 31 | mapDelivery | GET | /how-we-score | score_explanation_service | score |
| 32 | tourIdResolution | GET | /tour/{id}/resolve | home_screen | download (CORE) |
| 33 | userDb | GET | /user  and /user/{userId} | about_screen / tour_status_service | user |
| 34 | userDb | GET | /health | about_screen | diagnostics |
| 35 | userDb | GET | /entitlements/me | entitlements_service | entitlements |
| 36 | userDb | POST | /entitlements/app-open | entitlements_service | entitlements |
| 37 | userDb | POST | /entitlements/lapse | entitlements_service | entitlements |
| 38 | userDb | POST | /l2/queue/join | entitlements_service | entitlements |
| 39 | userDb | POST | /l2/claim | entitlements_service | entitlements |
| 40 | userDb | POST | /purchases/verify | iap_service | IAP |
| 41 | userDb | POST | /document-acceptance | document_acceptance_service | legal |
| 42 | userDb | GET | /document-acceptance?user_id=.. | document_acceptance_service | legal |
| 43 | userDb | POST | /communities | communities_service | communities |
| 44 | userDb | GET | /communities/by-code/{code} | communities_service | communities |
| 45 | userDb | GET | /communities/{id} | communities_service | communities |
| 46 | userDb | POST | /communities/{id}/join | communities_service | communities |
| 47 | userDb | GET | /communities/map | communities_service | communities |
| 48 | mapDelivery (treats) | GET | /treats-near/{lat}/{lng} | treats_screen | treats |
| 49 | treats | GET | /treats-near/{lat}/{lng} | treats_screen | treats |
| 50 | voice | POST | /parse_voice_search | my_tours_screen | voice search |
| 51 | voice | POST | /process-voice-command | voice_control_service | voice |
| 52 | translation | POST | /translate-with-audio | translation_service | translate (CORE) |
| 53 | generator | POST | /tour/share | tour_share_service | share (CORE) |
| 54 | news | POST | /generate-news | tour_generator_screen | news |
| 55 | news | GET | /news-status/{id} (cloud) /status/{id} (local) | tour_generator_screen | news |
| 56 | news | GET | /news-download/{id} (cloud) /download/{id} (local) | tour_generator_screen | news |
| 57 | newsletter | GET | /newsletters_v2 | home_screen | newsletter |
| 58 | newsletter | POST | /process_newsletter | home_screen | newsletter |
| 59 | newsletter | POST | /submit_credentials | subscription_service | subscription |
| 60 | newsletter | POST | /key_exchange | subscription_service | subscription |
| 61 | tourEditing | POST | /tour/{id}/update-stop | tour_editing_service | edit |
| 62 | tourEditing | POST | /tour/{id}/update-multiple-stops | tour_editing_service | edit |
| 63 | tourEditing | GET | /tour/{id}/job-status/{jobId} | tour_editing_service | edit |
| 64 | customAudio | POST | /tour/{id}/stop/{n}/custom-audio | custom_audio_service | custom audio |
| 65 | customAudio | DELETE | /tour/{id}/stop/{n}/custom-audio | custom_audio_service | custom audio |
| 66 | customAudio | GET | /tour/{id}/stop/{n}/audio-versions | custom_audio_service | custom audio |
| 67 | customAudio | GET | /tour/{id}/audio-metadata | custom_audio_service | custom audio |

Core flows (MUST work on Storied): map+tours-near (24), search (26), share code (27),
download & play (25, 32, 3), translate (52), generate (1,2,3), ratings (17,18), share (53).
