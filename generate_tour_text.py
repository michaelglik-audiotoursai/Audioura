"""
Modified version of generate_tour_text.py that includes geo coordinates for the first stop
"""
import os
import sys
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from enhanced_tour_templates_fixed import get_enhanced_tour_template, validate_enhanced_poi_knowledge
from poi_inclusion_exceptions import should_include_in_restaurant_tour, should_include_in_walking_tour
from tour_type_detector import detect_tour_type
from enhanced_prompt_generator import generate_enhanced_prompt
from datetime import datetime
import re

def analyze_tour_intent(user_request, api_key):
    """
    Enhanced AI-based intent analysis to detect specialized themes like books, movies, products.
    Cost: ~$0.0008 per analysis
    """
    intent_prompt = f"""Analyze this tour request and extract the key information:

Request: "{user_request}"

Please provide ONLY a JSON response with these fields:
{{
    "poi_type": "specific type of locations requested (e.g., restaurants, shops, stores, museums, book locations, movie filming sites, etc.)",
    "location": "geographic area",
    "theme_type": "BOOK/MOVIE/PRODUCT/STANDARD - identify if this is a themed tour",
    "theme_name": "name of book, movie, or specific product if applicable",
    "requirements": "any specific criteria mentioned",
    "business_hours_relevant": true/false,
    "accessibility_mentioned": true/false,
    "needs_research": true/false
}}

Examples:
- "Tour of restaurants in North End, Boston" → poi_type: "restaurants", theme_type: "STANDARD"
- "Walking tour based on Tomorrow and Tomorrow and Tomorrow book" → poi_type: "book locations", theme_type: "BOOK", theme_name: "Tomorrow, and Tomorrow, and Tomorrow"
- "Harry Potter filming locations in Boston" → poi_type: "filming locations", theme_type: "MOVIE", theme_name: "Harry Potter"
- "Fancy cheese shops in Cambridge" → poi_type: "cheese shops", theme_type: "PRODUCT", theme_name: "fancy cheese"
- "Stores selling vintage vinyl records" → poi_type: "record stores", theme_type: "PRODUCT", theme_name: "vintage vinyl records"
- "Bookstores mentioned in Little Women" → poi_type: "bookstores", theme_type: "BOOK", theme_name: "Little Women"
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a tour planning assistant. Respond only with valid JSON."},
            {"role": "user", "content": intent_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 200
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data)
        )
        
        if response.status_code == 200:
            result = response.json()
            intent_text = result["choices"][0]["message"]["content"]
            print(f"Intent analysis response: {intent_text}")
            return json.loads(intent_text)
        else:
            print(f"Intent analysis failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"Intent analysis error: {e}")
        return None

def validate_poi_knowledge(poi_list, intent, location, api_key):
    """
    Enhanced validation for specialized themes and generic POI detection.
    Returns True if knowledge is sufficient, False if insufficient.
    """
    if not poi_list or len(poi_list) == 0:
        return False, "No POIs were generated"
    
    # Enhanced generic patterns detection
    generic_patterns = [
        r'^(Store|Shop|Restaurant|Location|Exhibit|Building|Stop)\s+\d+$',
        r'^(Unknown|Generic|Sample)\s+',
        r'^[A-Za-z]+\s+\d+$',  # Single word + number pattern
        r'^Walking Tour \d+$',  # Specific pattern from the issue
        r'^Tour Stop \d+$',
        r'^Point \d+$'
    ]
    
    # Check for fictional content patterns (hallucinations)
    fictional_patterns = [
        r'sculpture titled "Tomorrow.*?Tomorrow.*?Tomorrow"',
        r'Created by renowned artist\s*,',  # Missing artist name
        r'stands the impressive.*?monumental work',
        r'fusion of art, history, and culture'
    ]
    
    generic_count = 0
    fictional_count = 0
    
    for poi in poi_list:
        poi_name = poi.get('name', '')
        poi_description = poi.get('description', '')
        
        # Check for generic names
        for pattern in generic_patterns:
            if re.match(pattern, poi_name):
                generic_count += 1
                break
        
        # Check for fictional/hallucinated content
        full_text = f"{poi_name} {poi_description}"
        for pattern in fictional_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                fictional_count += 1
                break
    
    # Enhanced validation for themed tours
    if intent and intent.get('theme_type') in ['BOOK', 'MOVIE']:
        theme_name = intent.get('theme_name', '')
        if generic_count > 0 or fictional_count > 0:
            return False, f"Unable to generate authentic locations for '{theme_name}'. The AI is creating fictional content instead of real locations. Please try a different theme or provide more specific location details."
    
    # Standard validation for regular tours
    if generic_count > len(poi_list) / 2:
        poi_type = intent.get('poi_type', 'locations') if intent else 'locations'
        return False, f"Insufficient data available for {poi_type} in {location}. Please try a different location or POI type."
    
    if fictional_count > 0:
        return False, f"AI generated fictional content instead of real locations. Please try a more specific request."
    
    return True, "Knowledge validation passed"

def verify_poi_matches_type(poi_name, poi_type, api_key):
    """
    Verify each POI matches the requested type.
    Cost: ~$0.0004 per POI
    """
    verification_prompt = f"""Is "{poi_name}" actually a {poi_type.rstrip('s')}?

Respond with ONLY a JSON object:
{{
    "matches": true/false,
    "reason": "brief explanation",
    "confidence": "high/medium/low"
}}

Example: For "Paul Revere House" and poi_type "restaurant":
{{"matches": false, "reason": "Paul Revere House is a historic museum, not a restaurant", "confidence": "high"}}
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a location verification assistant. Respond only with valid JSON."},
            {"role": "user", "content": verification_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 100
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data)
        )
        
        if response.status_code == 200:
            result = response.json()
            verification_text = result["choices"][0]["message"]["content"]
            return json.loads(verification_text)
        else:
            return {"matches": True, "reason": "verification failed", "confidence": "low"}
    except Exception as e:
        print(f"POI verification error: {e}")
        return {"matches": True, "reason": "verification failed", "confidence": "low"}

def detect_tour_type(location, tour_type):
    """
    Detect the appropriate tour template based on location and tour_type.
    
    Returns: 'restaurant', 'walking', 'museum', or 'specialized'
    """
    location_lower = location.lower()
    tour_type_lower = tour_type.lower()
    
    # Restaurant/Food tour detection (highest priority)
    food_keywords = ['restaurant', 'food', 'dining', 'culinary', 'eat', 'cafe', 'bistro', 'eatery']
    if any(keyword in location_lower or keyword in tour_type_lower for keyword in food_keywords):
        return 'restaurant'
    
    # Museum indicators
    museum_keywords = ['museum', 'gallery', 'mfa', 'moma', 'exhibition', 'collection', 'art center', 'cultural center']
    if any(keyword in location_lower for keyword in museum_keywords):
        return 'museum'
    
    # Specialized tour indicators
    specialized_keywords = ['book', 'movie', 'film', 'botanical', 'garden', 'park', 'novel', 'story', 'literary', 'filming']
    if any(keyword in tour_type_lower for keyword in specialized_keywords):
        return 'specialized'
    
    # Walking tour indicators (default for cities, neighborhoods)
    walking_keywords = ['city', 'downtown', 'neighborhood', 'district', 'street', 'avenue', 'center', 'town']
    if any(keyword in location_lower for keyword in walking_keywords):
        return 'walking'
    
    # Default to walking tour
    return 'walking'



def generate_tour_text(location, tour_type, output_file=None, total_stops=None):
    """
    Generate audio tour text using OpenAI API with geo coordinates.
    
    Args:
        location: Location for the tour
        tour_type: Type of tour (e.g., "sculpture", "architecture")
        output_file: File to save the tour text (optional)
        total_stops: Number of stops requested
    
    Returns:
        tuple: (tour_text, output_file, coordinates)
    """
    import api_call_logger
    api_call_logger.log("GENERATE_TOUR_TEXT_FUNCTION_ENTRY", {
        "location": location,
        "tour_type": tour_type,
        "total_stops_parameter": total_stops,
        "output_file": output_file,
    })
    # Get API key from environment variable or prompt user (only if interactive)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # Only prompt if running interactively (not from service)
        if __name__ == "__main__":
            api_key = input("Enter your OpenAI API key: ")
        if not api_key:
            print("Error: OpenAI API key is required")
            return None, None, (None, None)

    # Headers for API calls
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Get number of stops - only prompt if not provided
    if not total_stops:
        # Only prompt if running interactively (not from service)
        if __name__ == "__main__":
            total_stops = int(input("How many total stops would you like in the tour? (default: 10): ") or "10")
        else:
            total_stops = 10  # Default for service calls
    
    api_call_logger.log("TOTAL_STOPS_FINALIZED", {
        "location": location,
        "total_stops_final": total_stops,
        "source": "parameter" if total_stops else ("user_input" if __name__ == "__main__" else "service_default"),
    })
    
    # Track API costs
    total_tokens = 0
    total_cost = 0
    
    # PHASE 1: Analyze user intent with AI
    print(f"\nPHASE 1: Analyzing tour intent with AI...")
    user_request = f"{tour_type} {location}"
    intent = analyze_tour_intent(user_request, api_key)
    
    if intent:
        print(f"✅ Intent Analysis Results:")
        print(f"   POI Type: {intent.get('poi_type')}")
        print(f"   Location: {intent.get('location')}")
        print(f"   Requirements: {intent.get('requirements')}")
        print(f"   Business Hours Relevant: {intent.get('business_hours_relevant')}")
        print(f"   Accessibility Mentioned: {intent.get('accessibility_mentioned')}")
        
        # Use intelligent tour category detection
        tour_category = 'intelligent'
    else:
        print("⚠️ Intent analysis failed, using fallback detection")
        intent = None
        tour_category = detect_tour_type(location, tour_type)
    
    # PHASE 2: Detect tour type and get appropriate template
    tour_category = detect_tour_type(location, tour_type)
    print(f"\nDetected tour category: {tour_category.upper()}")
    print(f"Using {tour_category} template for {location} - {tour_type}")
    
    # ============================================================
    # PHASE 3A: Fetch candidate POI names + addresses (lightweight)
    # PHASE 4.5: Knowledge validation
    # PHASE 4:   Type verification (parallel, skipped for walking)
    # Part C:    Replacement loop (bounded retries)
    # PHASE 3B:  Ordering + structured details + directions
    # ============================================================
    poi_list = []
    first_poi_coordinates = (None, None)  # Default if we can't get coordinates

    # -------- Local helpers (closures over api_key, intent, tour_category) --------
    def _parse_json_array_loose(text):
        """Defensive JSON-array parsing: direct -> markdown-strip -> regex-extract."""
        if not text:
            return None
        t = text.strip()
        m = re.match(r'^```(?:json)?\s*(.*?)\s*```$', t, re.DOTALL)
        if m:
            t = m.group(1).strip()
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
        m = re.search(r'\[\s*\{.*\}\s*\]', t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None

    def _normalize_name(name):
        if not name:
            return ""
        return re.sub(r'\s+', ' ', name.strip()).lower()

    def _verify_against_intent(stops):
        """Run PHASE 4 type verification in parallel. Returns (survivors, excluded_count)."""
        if not (intent and intent.get('poi_type') and tour_category not in ('walking',)):
            return list(stops), 0
        if not stops:
            return [], 0

        print(f"   PHASE 4: Verifying {len(stops)} POI(s) against type '{intent['poi_type']}' (parallel)...")

        def _verify_one(poi):
            return poi, verify_poi_matches_type(poi["name"], intent["poi_type"], api_key)

        results = []
        with ThreadPoolExecutor(max_workers=min(len(stops), 5)) as executor:
            futures = {executor.submit(_verify_one, poi): poi for poi in stops}
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda x: stops.index(x[0]))

        survivors = []
        excluded = 0
        for poi, verification in results:
            if verification["matches"] or verification["confidence"] == "low":
                survivors.append(poi)
                if verification["matches"]:
                    print(f"   OK Verified {poi['name']} - {verification['reason']}")
                else:
                    print(f"   OK Included {poi['name']} (verification failed, low confidence)")
            else:
                poi_desc = poi.get("description", "") or ""
                if "restaurant" in intent["poi_type"].lower() or "food" in intent["poi_type"].lower():
                    should, reason = should_include_in_restaurant_tour(poi["name"], poi_desc, verification["reason"])
                else:
                    should, reason = should_include_in_walking_tour(poi["name"], poi_desc, verification["reason"])
                if should:
                    survivors.append(poi)
                    print(f"   OK Included {poi['name']} - {reason}")
                else:
                    excluded += 1
                    print(f"   X  Excluded {poi['name']} - {verification['reason']}")
        return survivors, excluded

    def _new_poi(name, address=""):
        return {
            "stop_number": 0,
            "name": (name or "").strip(),
            "address": (address or "").strip(),
            "artist": "",
            "year": "",
            "directions": "",
            "coordinates": "",
            "type_specialty": "",
            "specific_examples": "",
            "operational_details": "",
            "description": "",
        }

    # Determine poi_type hint for prompts
    if intent and intent.get('poi_type'):
        poi_type_hint = intent['poi_type']
    else:
        poi_type_hint = f"{tour_type} stops"

    if tour_type.lower() in location.lower():
        user_request = location
    else:
        user_request = f"{tour_type} {location}"

    api_call_logger.log("GENERATING_PROMPT", {
        "location": location,
        "user_request": user_request,
        "total_stops": total_stops,
    })

    # -------- PHASE 3A: names + addresses only --------
    print(f"\nPHASE 3A: Fetching {total_stops} candidate POI(s) for {location}...")
    phase_3a_prompt = (
        f"You are a knowledgeable local guide for {location}.\n"
        f"List exactly {total_stops} specific, real, well-known {poi_type_hint} relevant to: {user_request}.\n\n"
        "Requirements:\n"
        "- Use REAL, SPECIFIC names of actual establishments or landmarks.\n"
        "- NEVER use generic placeholders like 'Restaurant 1', 'Stop 1', 'Location A'.\n"
        "- Include a complete street address with ZIP code where applicable.\n\n"
        "Return ONLY a JSON array, no other text, no markdown fences:\n"
        '[{"name": "...", "address": "..."}, ...]'
    )
    phase_3a_data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You return ONLY a valid JSON array. No markdown, no commentary."},
            {"role": "user", "content": phase_3a_prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 800,
    }
    api_call_logger.log("PHASE_3A_REQUEST", {
        "location": location,
        "total_stops": total_stops,
        "poi_type_hint": poi_type_hint,
    })

    try:
        info_response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(phase_3a_data),
        )
        if info_response.status_code != 200:
            print(f"X PHASE 3A failed: status {info_response.status_code}")
            print(info_response.text)
            return None, None, (None, None)

        info_result = info_response.json()
        info_text = info_result["choices"][0]["message"]["content"]
        tokens_used = info_result["usage"]["total_tokens"]
        total_tokens += tokens_used
        total_cost += tokens_used / 1000 * 0.002
        print(f"PHASE 3A API call cost: ${tokens_used / 1000 * 0.002:.4f} ({tokens_used} tokens)")

        api_call_logger.log_openai_call(phase_3a_prompt, total_stops, info_text, info_response.status_code)

        with open("openai_simple_debug.txt", "w", encoding="utf-8") as simple_debug:
            simple_debug.write("=== EXACT PROMPT SENT TO OPENAI (PHASE 3A) ===\n")
            simple_debug.write(phase_3a_prompt)
            simple_debug.write("\n\n=== OPENAI RESPONSE ===\n")
            simple_debug.write(info_text)
            simple_debug.write(f"\n\n=== ANALYSIS ===\nRequested stops: {total_stops}\n")
            simple_debug.write(f"See full chain log: {api_call_logger.get_log_path()}\n")

        # Insufficient-knowledge detection (kept from previous behaviour)
        insufficient_knowledge_indicators = [
            "I don't have sufficient knowledge",
            "I am unable to provide",
            "I cannot provide real-time information",
            "insufficient data available",
            "I don't know actual locations",
            "I lack specific knowledge",
        ]
        for indicator in insufficient_knowledge_indicators:
            if indicator.lower() in info_text.lower():
                print(f"X AI KNOWLEDGE INSUFFICIENT: {info_text[:200]}...")
                return None, None, (None, None)

        candidates = _parse_json_array_loose(info_text)
        if not candidates or not isinstance(candidates, list):
            print(f"X PHASE 3A returned unparseable response: {info_text[:300]}")
            return None, None, (None, None)

        for c in candidates:
            if not isinstance(c, dict):
                continue
            name = (c.get("name") or "").strip()
            if not name:
                continue
            if re.match(r'^(Restaurant|Store|Shop|Location|Business|Walking Tour)\s*\d*$', name):
                print(f"   ! Rejected generic name from PHASE 3A: '{name}'")
                continue
            poi_list.append(_new_poi(name, c.get("address") or ""))

        if len(poi_list) == 0:
            print(f"X PHASE 3A: no usable POIs after parsing")
            return None, None, (None, None)

        print(f"OK PHASE 3A parsed {len(poi_list)} candidate POI(s):")
        for p in poi_list:
            print(f"   - {p['name']}" + (f" @ {p['address']}" if p['address'] else ""))

        # -------- PHASE 4.5: knowledge validation --------
        print(f"\nPHASE 4.5: Validating AI knowledge for {location}...")
        knowledge_valid, knowledge_message = validate_enhanced_poi_knowledge(poi_list, intent, location)
        if not knowledge_valid:
            print(f"X Knowledge validation failed: {knowledge_message}")
            return None, None, (None, None)
        print(f"OK Knowledge validation passed: {knowledge_message}")

        # Snapshot before PHASE 4
        poi_list_before_verification = list(poi_list)

        # -------- PHASE 4: parallel type verification (skipped for walking) --------
        if intent and intent.get('poi_type') and tour_category not in ('walking',):
            print(f"\nPHASE 4: Verifying POIs match requested type '{intent['poi_type']}' (parallel)...")
            poi_list, excluded_count = _verify_against_intent(poi_list)
            if excluded_count > 0:
                print(f"\n! PHASE 4 excluded {excluded_count} POI(s)")
        else:
            excluded_count = 0
            print(f"\nPHASE 4: skipped (tour_category='{tour_category}', no type-verification required)")

        excluded_names = {p["name"] for p in poi_list_before_verification if p not in poi_list}

        # -------- Part C: replacement loop (bounded) --------
        MAX_REPLACEMENT_ATTEMPTS = 2
        attempts = 0
        # Build "forbidden" name set (normalized): everything ever proposed PLUS exclusions
        forbidden_norms = set()
        for p in poi_list_before_verification:
            forbidden_norms.add(_normalize_name(p["name"]))
        for p in poi_list:
            forbidden_norms.add(_normalize_name(p["name"]))

        while len(poi_list) < total_stops and attempts < MAX_REPLACEMENT_ATTEMPTS:
            attempts += 1
            needed = total_stops - len(poi_list)
            print(f"\nPart C: Fetching {needed} replacement POI(s), attempt {attempts}/{MAX_REPLACEMENT_ATTEMPTS}...")

            # Build the "do not use" list of original-cased names for the prompt
            forbidden_display = sorted(set(
                p["name"] for p in poi_list_before_verification
            ) | set(
                p["name"] for p in poi_list
            ) | set(excluded_names))
            forbidden_str = "; ".join(forbidden_display) if forbidden_display else "(none)"

            replacement_prompt = (
                f"You are a knowledgeable local guide for {location}.\n"
                f"Suggest exactly {needed} additional specific, real, well-known {poi_type_hint} in {location}.\n"
                f"DO NOT include any of these already-used or rejected names: {forbidden_str}.\n\n"
                "Requirements:\n"
                "- REAL, SPECIFIC names; never generic placeholders.\n"
                "- Complete street address with ZIP where applicable.\n\n"
                "Return ONLY a JSON array, no other text:\n"
                '[{"name": "...", "address": "..."}, ...]'
            )
            replacement_data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You return ONLY a valid JSON array. No markdown, no commentary."},
                    {"role": "user", "content": replacement_prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500,
            }
            try:
                rep_response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    data=json.dumps(replacement_data),
                )
                if rep_response.status_code != 200:
                    print(f"   Part C attempt {attempts}: API error {rep_response.status_code}")
                    continue
                rep_result = rep_response.json()
                rep_text = rep_result["choices"][0]["message"]["content"]
                tokens_used = rep_result["usage"]["total_tokens"]
                total_tokens += tokens_used
                total_cost += tokens_used / 1000 * 0.002

                new_candidates = _parse_json_array_loose(rep_text)
                if not new_candidates or not isinstance(new_candidates, list):
                    print(f"   Part C attempt {attempts}: unparseable response")
                    continue

                new_stops = []
                for c in new_candidates:
                    if not isinstance(c, dict):
                        continue
                    name = (c.get("name") or "").strip()
                    if not name:
                        continue
                    if re.match(r'^(Restaurant|Store|Shop|Location|Business|Walking Tour)\s*\d*$', name):
                        continue
                    norm = _normalize_name(name)
                    if norm in forbidden_norms:
                        continue
                    new_stops.append(_new_poi(name, c.get("address") or ""))
                    forbidden_norms.add(norm)

                print(f"   Part C attempt {attempts}: AI returned {len(new_stops)} usable candidate(s)")

                # Verify the new stops too (same PHASE 4 logic)
                survived, _ = _verify_against_intent(new_stops)
                survived = survived[:needed]
                poi_list.extend(survived)
                # forbid every attempted name so subsequent attempts diverge
                for p in new_stops:
                    forbidden_norms.add(_normalize_name(p["name"]))
                print(f"   Part C attempt {attempts}: {len(survived)} survived; total now {len(poi_list)}")
            except Exception as e:
                print(f"   Part C attempt {attempts}: exception {e}")
                continue

        # Hard cap and final sanity
        if len(poi_list) > total_stops:
            poi_list = poi_list[:total_stops]
        if len(poi_list) == 0:
            print(f"X All POIs were filtered out; cannot continue")
            return None, None, (None, None)
        if len(poi_list) < total_stops:
            print(f"! Final count {len(poi_list)} < requested {total_stops}; orchestrator will surface stop_count_warning")

        for i, p in enumerate(poi_list):
            p["stop_number"] = i + 1

        # -------- PHASE 3B: ordering + structured details + directions --------
        print(f"\nPHASE 3B: Requesting structured details and walking directions for {len(poi_list)} stop(s)...")

        survivors_lines = []
        for p in poi_list:
            line = f'- {p["name"]}'
            if p.get("address"):
                line += f' (Address: {p["address"]})'
            survivors_lines.append(line)
        survivors_block = "\n".join(survivors_lines)

        phase_3b_prompt = (
            f"For a tour of {location}, the following {len(poi_list)} stop(s) have been selected:\n"
            f"{survivors_block}\n\n"
            "Reorder them for an OPTIMAL walking route (minimise backtracking).\n"
            "For each stop in the NEW order, provide all the JSON fields below.\n"
            "For stop #1, 'directions_from_previous' should describe how to reach it from a reasonable arrival point (T station, parking, main street).\n"
            "For subsequent stops, 'directions_from_previous' should be turn-by-turn walking directions from the IMMEDIATELY PREVIOUS stop in the new order.\n\n"
            "Return ONLY a JSON array, no markdown fences, no commentary:\n"
            "[\n"
            "  {\n"
            '    "name": "<must match one of the input names exactly>",\n'
            '    "address": "<complete street address with ZIP>",\n'
            '    "coordinates": "<lat, lng in decimal format>",\n'
            '    "type_specialty": "<short type/specialty description>",\n'
            '    "specific_examples": "<2-3 concrete examples of what visitors will see/experience>",\n'
            '    "operational_details": "<hours, prices, reservations, busy times>",\n'
            '    "directions_from_previous": "<turn-by-turn>"\n'
            "  }\n"
            "]"
        )
        phase_3b_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You return ONLY a valid JSON array. No markdown, no commentary."},
                {"role": "user", "content": phase_3b_prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 2000,
        }
        api_call_logger.log("PHASE_3B_REQUEST", {
            "location": location,
            "stop_count": len(poi_list),
        })

        try:
            b_response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                data=json.dumps(phase_3b_data),
            )
            if b_response.status_code != 200:
                print(f"! PHASE 3B failed (status {b_response.status_code}); keeping PHASE 3A order, generic directions will be used.")
            else:
                b_result = b_response.json()
                b_text = b_result["choices"][0]["message"]["content"]
                tokens_used = b_result["usage"]["total_tokens"]
                total_tokens += tokens_used
                total_cost += tokens_used / 1000 * 0.002
                print(f"PHASE 3B API call cost: ${tokens_used / 1000 * 0.002:.4f} ({tokens_used} tokens)")

                parsed = _parse_json_array_loose(b_text)
                if not parsed or not isinstance(parsed, list):
                    print(f"! PHASE 3B unparseable response; keeping PHASE 3A order, generic directions will be used.")
                else:
                    # Validation: canonicalize names, flag unknowns, append missing
                    canonical_by_norm = {_normalize_name(p["name"]): p["name"] for p in poi_list}
                    parsed_normalized = []
                    unknown = []
                    for entry in parsed:
                        if not isinstance(entry, dict):
                            continue
                        norm = _normalize_name(entry.get("name", ""))
                        if norm in canonical_by_norm:
                            entry["name"] = canonical_by_norm[norm]
                            parsed_normalized.append(entry)
                        else:
                            unknown.append(entry.get("name", ""))

                    if unknown:
                        print(f"! PHASE 3B introduced unknown names (ignored): {unknown}")

                    if len(parsed_normalized) == 0:
                        print(f"! PHASE 3B produced no recognisable entries; keeping PHASE 3A order")
                    else:
                        # Append any original POI that the AI dropped
                        present_norms = {_normalize_name(e["name"]) for e in parsed_normalized}
                        for orig in poi_list:
                            if _normalize_name(orig["name"]) not in present_norms:
                                print(f"! PHASE 3B dropped POI; re-appending at end: {orig['name']}")
                                parsed_normalized.append({
                                    "name": orig["name"],
                                    "address": orig.get("address", ""),
                                    "coordinates": "",
                                    "type_specialty": "",
                                    "specific_examples": "",
                                    "operational_details": "",
                                    "directions_from_previous": "",
                                })

                        # Cap to total_stops
                        if len(parsed_normalized) > total_stops:
                            parsed_normalized = parsed_normalized[:total_stops]

                        # Merge: PHASE 3B order is authoritative
                        new_poi_list = []
                        for idx, entry in enumerate(parsed_normalized):
                            norm = _normalize_name(entry["name"])
                            orig = next((p for p in poi_list if _normalize_name(p["name"]) == norm), None)
                            merged = _new_poi(entry["name"], entry.get("address") or (orig.get("address") if orig else ""))
                            merged["stop_number"] = idx + 1
                            merged["directions"] = (entry.get("directions_from_previous") or "").strip()
                            merged["coordinates"] = (entry.get("coordinates") or "").strip()
                            merged["type_specialty"] = (entry.get("type_specialty") or "").strip()
                            merged["specific_examples"] = (entry.get("specific_examples") or "").strip()
                            merged["operational_details"] = (entry.get("operational_details") or "").strip()
                            new_poi_list.append(merged)
                        poi_list = new_poi_list
                        print(f"OK PHASE 3B: ordered {len(poi_list)} stop(s) with structured details and directions")
        except Exception as e:
            print(f"! PHASE 3B exception: {e}; keeping PHASE 3A order")

        # -------- Coordinates for the first POI (used by orchestrator) --------
        if poi_list and poi_list[0].get("coordinates"):
            try:
                coords_text = poi_list[0]["coordinates"]
                coord_match = re.search(r'(\d+\.\d+)\s*[°]?\s*([NS]).*?(\d+\.\d+)\s*[°]?\s*([EW])', coords_text, re.IGNORECASE)
                if coord_match:
                    lat = float(coord_match.group(1))
                    if coord_match.group(2).upper() == 'S':
                        lat = -lat
                    lng = float(coord_match.group(3))
                    if coord_match.group(4).upper() == 'W':
                        lng = -lng
                    first_poi_coordinates = (lat, lng)
                else:
                    nums = re.findall(r'-?\d+\.\d+', coords_text)
                    if len(nums) >= 2:
                        first_poi_coordinates = (float(nums[0]), float(nums[1]))
                if first_poi_coordinates != (None, None):
                    print(f"Extracted first POI coordinates: {first_poi_coordinates}")
            except Exception as e:
                print(f"Error parsing first POI coordinates: {e}")

        if first_poi_coordinates == (None, None) and poi_list:
            print("No coordinates from PHASE 3B; requesting specifically for first POI...")
            coords_prompt = (
                f"Please provide the GPS coordinates (latitude and longitude) for "
                f"{poi_list[0]['name']} at {location}.\n\n"
                "Format your response as:\nLatitude: [number]\nLongitude: [number]\n\n"
                "ONLY provide the coordinates, nothing else."
            )
            coords_data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that provides accurate GPS coordinates."},
                    {"role": "user", "content": coords_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 100,
            }
            try:
                coords_response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    data=json.dumps(coords_data),
                )
                if coords_response.status_code == 200:
                    coords_result = coords_response.json()
                    coords_text = coords_result["choices"][0]["message"]["content"]
                    tokens_used = coords_result["usage"]["total_tokens"]
                    total_tokens += tokens_used
                    total_cost += tokens_used / 1000 * 0.002

                    lat_match = re.search(r'Latitude:\s*(-?\d+\.\d+)', coords_text, re.IGNORECASE)
                    lng_match = re.search(r'Longitude:\s*(-?\d+\.\d+)', coords_text, re.IGNORECASE)
                    if lat_match and lng_match:
                        first_poi_coordinates = (float(lat_match.group(1)), float(lng_match.group(1)))
                        poi_list[0]["coordinates"] = f"{first_poi_coordinates[0]}, {first_poi_coordinates[1]}"
                        print(f"Extracted coordinates for first POI: {first_poi_coordinates}")
            except Exception as e:
                print(f"Error requesting coordinates: {e}")

        # Print extracted POI information
        print("\n=== Extracted POI Information ===")
        for p in poi_list:
            print(f"{p['stop_number']}. {p['name']}")
            if p.get('address'):
                print(f"   Address: {p['address']}")
            if p.get('coordinates'):
                print(f"   Coordinates: {p['coordinates']}")
            if p.get('directions'):
                snippet = p['directions'][:80] + ('...' if len(p['directions']) > 80 else '')
                print(f"   Directions: {snippet}")
        print("================================\n")

    except Exception as e:
        print(f"Error in PHASE 3A/3B pipeline: {str(e)}")
        import traceback
        traceback.print_exc()
        if intent:
            poi_type = intent.get('poi_type', 'locations')
            print(f"X Unable to generate tour: Insufficient data available for {poi_type} in {location}.")
            return None, None, (None, None)
        # Last-resort fallback (no intent): keep behaviour for robustness
        for i in range(total_stops):
            poi_list.append({
                "stop_number": i + 1,
                "name": f"Location {i + 1}",
                "artist": "",
                "year": "",
                "directions": "",
                "coordinates": "",
                "description": "",
            })
    
    # PHASE 5: Generate detailed descriptions for each POI (parallelized)
    print(f"\nPHASE 5: Generating detailed descriptions for each POI (parallel)...")

    def _generate_description(args):
        idx, poi = args
        stop_num = idx + 1
        poi_name = poi["name"]
        artist = poi["artist"]
        year = poi["year"]

        print(f"\nGenerating description for Stop {stop_num}: {poi_name} by {artist}, {year}...")

        description_prompt = f"""Create a detailed description for {poi_name} in a walking tour of {location} focusing on {tour_type}.

Start with an orientation section that explains where the visitor should position themselves to best view and appreciate this exhibit.

Then provide a detailed description of the exhibit that is EXACTLY 300 words long. Include:
- The artistic, historical, and cultural significance of the work
- Information about the artist and their creative process
- How this piece fits into the broader context of {tour_type}
- Interesting details that would engage visitors

Format your response as follows:
Orientation: [Brief orientation text explaining the best viewing position]

[Detailed 300-word description of the exhibit]

DO NOT include any section headers other than "Orientation:" - the description should flow naturally after the orientation section.
DO NOT include directions to the next stop - these will be added separately.
"""

        description_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a knowledgeable museum guide with expertise in art, architecture, and history."},
                {"role": "user", "content": description_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }

        try:
            description_response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                data=json.dumps(description_data)
            )

            if description_response.status_code == 200:
                description_result = description_response.json()
                description_text = description_result["choices"][0]["message"]["content"]

                tokens_used = description_result["usage"]["total_tokens"]
                call_cost = tokens_used / 1000 * 0.002
                print(f"Stop {stop_num} API call cost: ${call_cost:.4f} ({tokens_used} tokens)")

                parts = description_text.split("Orientation:", 1)
                if len(parts) > 1:
                    orientation_text = parts[1].strip()
                    description_parts = orientation_text.split("\n\n", 1)
                    if len(description_parts) > 1:
                        orientation = description_parts[0].strip()
                        description = description_parts[1].strip()
                    else:
                        orientation = orientation_text
                        description = ""
                else:
                    orientation = "Position yourself directly in front of the exhibit for the best view."
                    description = description_text.strip()

                word_count = len(description.split())
                print(f"Stop {stop_num} description word count: {word_count} words")
                return idx, orientation, description, word_count, tokens_used, call_cost
            else:
                print(f"Stop {stop_num} error: API returned status code {description_response.status_code}")
                return idx, "Position yourself directly in front of the exhibit for the best view.", f"[Description for {poi_name} could not be generated.]", 0, 0, 0.0

        except Exception as e:
            print(f"Stop {stop_num} error: {str(e)}")
            return idx, "Position yourself directly in front of the exhibit for the best view.", f"[Description for {poi_name} could not be generated.]", 0, 0, 0.0

    max_workers = min(len(poi_list), 5)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_generate_description, (i, poi)): i for i, poi in enumerate(poi_list)}
        for future in as_completed(futures):
            idx, orientation, description, word_count, tokens_used, call_cost = future.result()
            poi_list[idx]["orientation"] = orientation
            poi_list[idx]["description"] = description
            poi_list[idx]["word_count"] = word_count
            total_tokens += tokens_used
            total_cost += call_cost
    
    # PHASE 6: Assemble the complete tour
    print(f"\nPHASE 4: Assembling the complete tour...")
    
    # Create a better title that doesn't duplicate information
    if tour_type.lower() in location.lower():
        # If tour type is already in the location name, don't repeat it
        tour_title = f"Step-by-Step Audio Guided Tour: {location}"
    else:
        # Otherwise, create a title that incorporates the tour type naturally
        tour_title = f"Step-by-Step Audio Guided Tour: {location} - {tour_type.title()} Tour"
    
    complete_tour = tour_title + "\n\n"
    
    # Add each POI with its description and directions
    for i, poi in enumerate(poi_list):
        stop_num = i + 1   # always sequential; ignore whatever AI emitted
        poi_name = poi["name"]
        artist = poi["artist"]
        year = poi["year"]
        orientation = poi.get("orientation", "Position yourself to best view this location.")
        # Strip any "Stop N:" prefix the AI may have echoed into the orientation text
        orientation = re.sub(r'^Stop\s+\d+:\s*', '', orientation, count=1, flags=re.IGNORECASE).strip()
        if not orientation:
            orientation = "Position yourself to best view this location."
        description = poi.get("description", f"[Description for {poi_name} could not be generated.]")
        
        # Format the POI header
        poi_header = f"Stop {stop_num}: {poi_name}"
        if artist and artist.lower() != "unknown artist":
            poi_header += f" by {artist}"
        if year:
            poi_header += f", {year}"
        
        # Start the POI content with all extracted information
        poi_content = poi_header + "\n\n"
        
        # Add address if available
        if poi.get("address"):
            poi_content += f"Address: {poi['address']}\n\n"
        
        # Add coordinates if available (first stop only)
        if i == 0 and poi.get("coordinates"):
            poi_content += f"Coordinates: {poi['coordinates']}\n\n"
        
        # Add type/specialty if available
        if poi.get("type_specialty"):
            poi_content += f"Type/Specialty: {poi['type_specialty']}\n\n"
        
        # Add specific examples if available
        if poi.get("specific_examples"):
            poi_content += f"Specific Examples: {poi['specific_examples']}\n\n"
        
        # Add operational details if available
        if poi.get("operational_details"):
            poi_content += f"Operational Details: {poi['operational_details']}\n\n"
        
        print(f"  DEBUG - POI {stop_num} content includes:")
        print(f"    Specific Examples: {bool(poi.get('specific_examples'))}")
        print(f"    Operational Details: {bool(poi.get('operational_details'))}")
        print(f"    Walking Directions: {bool(poi.get('directions'))}")
        
        # Add orientation section
        poi_content += "Orientation: "
        if i == 0:
            # For the first POI, include directions from the entrance
            entrance_directions = poi.get("directions", "")
            if entrance_directions:
                poi_content += entrance_directions + " "
        
        # Add the orientation text
        poi_content += orientation + "\n\n"
        
        # Add description
        poi_content += description + "\n\n"
        
        # Add directions to next stop or conclusion
        if i < len(poi_list) - 1:
            next_poi = poi_list[i + 1]
            directions = next_poi.get("directions", "")
            
            # Debug: Print the directions
            print(f"DEBUG - Directions for Stop {stop_num} to {stop_num+1}: '{directions}'")
            
            # Always include the standard phrase
            poi_content += "Please resume the tour at the next stop once you reach it by following these directions: "
            
            # CRITICAL FIX: Use the CURRENT POI's directions to get TO the next POI
            # The directions should be stored in the NEXT POI but describe how to get there FROM current POI
            if directions and directions.strip() and "Continue to" not in directions:
                # Use the detailed walking directions provided by AI
                poi_content += directions.strip()
                print(f"  ✅ Using detailed walking directions: {directions[:50]}...")
            else:
                # Fallback to generic direction only if no detailed directions available
                poi_content += f"Continue to the next location, '{next_poi['name']}'."
                print(f"  ⚠️ Using generic directions - no detailed directions found")
        else:
            # For the last POI, add the conclusion
            if tour_type.lower() in location.lower():
                # If tour type is already in the location name, don't repeat it
                conclusion = f"Thank you for joining this tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
            else:
                conclusion = f"Thank you for joining this {tour_type} tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
            
            poi_content += conclusion
        
        # Add to complete tour
        complete_tour += poi_content + "\n\n"
    
    # Print word count statistics
    print("\n=== Word Count Statistics ===")
    for poi in poi_list:
        print(f"Stop {poi['stop_number']}: {poi['name']} - {poi['word_count']} words")
    print("===========================\n")
    
    # Print total cost
    print(f"\nTotal API cost: ${total_cost:.4f} ({total_tokens} tokens)")
    
    # Save to file if output_file is provided
    if not output_file:
        # Create default filename based on location and tour type
        safe_location = ''.join(c if c.isalnum() else '_' for c in location)
        safe_tour_type = ''.join(c if c.isalnum() else '_' for c in tour_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{safe_location}_{safe_tour_type}_tour_{timestamp}.txt"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(complete_tour)
    
    print(f"\nTour text generated successfully!")
    print(f"Saved to: {output_file}")
    
    # Show a preview
    preview_length = min(500, len(complete_tour))
    print(f"\nPreview of the generated tour:\n")
    print(complete_tour[:preview_length] + "...\n")
    
    return complete_tour, output_file, first_poi_coordinates

if __name__ == "__main__":
    print("=== Audio Tour Generator with Coordinates ===\n")
    
    # Get location
    location = input("Enter the location (e.g., 'deCordova Sculpture Park in Lincoln, MA'): ")
    if not location:
        location = "deCordova Sculpture Park in Lincoln, MA"
        print(f"Using default location: {location}")
    
    # Get tour type
    tour_type = input("Enter the tour focus (e.g., 'sculpture', 'architecture'): ")
    if not tour_type:
        tour_type = "sculpture"
        print(f"Using default tour focus: {tour_type}")
    
    # Get output file (optional)
    output_file = input("Enter output file name (press Enter for auto-generated): ")
    
    # Generate the tour text
    tour_text, output_file, coordinates = generate_tour_text(location, tour_type, output_file)
    
    print(f"First POI coordinates: {coordinates}")