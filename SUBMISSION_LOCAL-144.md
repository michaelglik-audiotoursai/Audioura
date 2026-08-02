##### READY FOR REVIEW

**Task:** LOCAL-144  
**Agent:** Mac Mini Kiro  
**Branch:** kiro/local144-seam-audit  
**Base:** storied  
**Commit:** 53a0244

---

## Changes (round 2)

| File | Change |
|------|--------|
| `UNREACHED_CODE_AUDIT.md` | Revised — three categories, import-verified swallowed-exception table, corrected rankings |

---

## What changed from round 1

1. **Added Category B ("works today, fails silently tomorrow").** Practical facts QA gate and walking directions moved here with import evidence showing they currently work. They are not broken — their failure alarm is disconnected.

2. **Re-ranked by real user impact.** Category A (wired-wrong) is ranked by features that are dead RIGHT NOW:
   - Rank 1: Tour editing (confirmed dead, app calls non-existent backend)
   - Rank 2: Subscription credential pipeline (3 modules, zero deployment)
   - Rank 3: Newsletter processor (old compose only)
   - Rank 4: Translation ZIP validation (corrupt ZIPs silently pass — runtime, not import)

3. **Full swallowed-exception table with import verification.** Every `except...: pass` around an import or registration, each tested with an actual `python3 -c "from X import Y"`. 11 locations tested. Results:
   - 10 IMPORTS-OK (features currently work)
   - 1 IMPORTS-FAIL (`browser_automation` — no selenium on host; irrelevant, module not reachable from any running service)

4. **Fixed duplicated dead-code row** (`poi_inclusion_exceptions_raw.py` appeared twice).

5. **Corrected voice_nlp_service and tour_hook_generator.** Both moved to dead code — their features are provided by other modules (`voice_control/app.py` and inline prolog generation respectively). Original report overstated impact.

---

## Evidence

### Import verification (ran on host)
```
practical_facts_gate           IMPORTS OK   extract_practical_claims: True
directions_generator           IMPORTS OK   generate_walking_directions: True
content_qa_runner              IMPORTS OK
generate_tour_text._LAST_CLEAN_FAIL_EVIDENCE  IMPORTS OK
generate_tour_text._LAST_VERIFICATION_TIER    IMPORTS OK
generate_tour_text._LAST_POI_LIST             IMPORTS OK
cost_meter                     IMPORTS OK   record_operation: True
sharing_endpoints              IMPORTS OK   sharing_bp: True
referral_endpoints             IMPORTS OK   referral_bp: True
persona_endpoints              IMPORTS OK   persona_bp: True
deeplink_resolution_endpoint   IMPORTS OK   deeplink_bp: True
swipe_preference_service       IMPORTS OK   register_preference_routes: True
browser_automation             IMPORTS FAIL  ModuleNotFoundError: No module named 'selenium'
```

### Tour editing NOT in master compose
```
$ grep -i "tour.edit\|5020\|5022" docker-compose-master.yml
(no output — zero matches)

$ grep -i "tour.edit\|5020\|5022" docker-compose.yml
  tour-editing:
    container_name: tour-editing-1
      - "5020:5020"
    command: python tour_editing_simple.py
  tour-editing-phase2:
    container_name: tour-editing-phase2-1
      - "5022:5022"
    command: python tour_editing_phase2.py
```

### Mobile app calls port 5022
```
audio_tour_app/lib/config/endpoints.dart:30:    Service.tourEditing: 5022,
audio_tour_app/lib/screens/edit_stop_screen.dart:9:import '../services/tour_editing_service.dart';
audio_tour_app/lib/screens/edit_tour_screen.dart:8:import '../services/tour_editing_service.dart';
```

---

## Limitations

- Imports tested on host Python 3.9, not inside containers. A module that loads on the host may fail in a container with different deps.
- Cloud Run paths not audited.
- Flutter/Dart dead code not audited beyond backend-calling confirmation.
- "IMPORTS-OK" confirms the module loads — not that the code executes correctly at runtime.
- Dynamic dispatch (`getattr`, `importlib`) would be invisible to this method.
