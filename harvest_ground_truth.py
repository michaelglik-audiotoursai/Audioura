"""
LOCAL-446 — Harvest ground truth from live Wikimedia.

Builds a 40-entity fixture with data from Wikidata (wbsearchentities, P856)
and Wikipedia (page/summary extract). This is the comparison baseline.

Composition (per task spec):
  - 15 well-known venues/institutions
  - 15 individual works/objects from real tours (long tail)
  - 10 French-language entities

Respects Wikimedia rate limits: 1 second between calls.
If a 429 is encountered, waits 60 seconds and resumes.
"""

import json
import os
import sys
import time
import logging
import requests
from urllib.parse import quote
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

USER_AGENT = "AudiouraBot/2.2 (LOCAL-446-measurement; contact: support@audioura.com)"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "ground_truth_entities.json")

# --- The 40 entities ---

# 15 well-known venues/institutions
WELL_KNOWN_VENUES = [
    "Museum of Fine Arts, Boston",
    "Palais Lascaris",
    "Centre Pompidou",
    "Musée Matisse Nice",
    "Uffizi Gallery",
    "Musée National Marc Chagall",
    "Musée d'Orsay",
    "The Metropolitan Museum of Art",
    "Louvre",
    "British Museum",
    "Rijksmuseum",
    "Galleria Borghese",
    "Musée Picasso Paris",
    "Hermitage Museum",
    "National Gallery London",
]

# 15 individual works/objects — long tail from real tours
LONG_TAIL_WORKS = [
    "Paolo Antonio Testore",          # Luthier, Palais Lascaris instrument
    "La Joie de Vivre (Picasso)",     # Antibes painting
    "The Dance (Matisse)",            # Famous Matisse painting
    "Fruitlands Museum",              # Small Massachusetts museum
    "Villa Ephrussi de Rothschild",   # Cap Ferrat villa
    "Chapelle du Rosaire de Vence",   # Matisse chapel
    "Cathédrale Sainte-Réparate de Nice",  # Nice cathedral
    "Promenade du Paillon",           # Nice park
    "Fort du Mont Alban",             # Nice fortress
    "Monastère de Cimiez",            # Nice monastery
    "Musée de la Castre",             # Cannes museum
    "Opéra de Nice",                  # Nice opera house
    "Le Negresco",                    # Famous Nice hotel
    "Cours Saleya",                   # Nice market street
    "Colline du Château Nice",        # Castle Hill Nice
]

# 10 French-language entities (accent-folded comparison per D243)
FRENCH_ENTITIES = [
    "Église Saint-Jacques-le-Majeur de Nice",
    "Théâtre National de Nice",
    "Musée d'Art Moderne et d'Art Contemporain de Nice",
    "Palais de la Méditerranée",
    "Basilique Notre-Dame de Nice",
    "Place Masséna",
    "Hôtel de Ville de Nice",
    "Musée des Beaux-Arts de Nice",
    "Conservatoire de Nice",
    "Bibliothèque Louis Nucéra",
]


def _wait_for_rate_limit(last_call_time: float, min_interval: float = 1.0) -> float:
    """Ensure minimum interval between calls. Returns new last_call_time."""
    elapsed = time.time() - last_call_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    return time.time()


def _handle_429(attempt: int = 1):
    """Handle a 429 response: wait and allow retry."""
    wait_time = 60 * attempt
    logger.warning(f"Got 429 — waiting {wait_time}s before resuming...")
    time.sleep(wait_time)


def search_wikidata_entity(entity_name: str) -> Optional[dict]:
    """wbsearchentities call — returns {qid, label, description} or None."""
    for attempt in range(1, 4):
        try:
            resp = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbsearchentities",
                    "search": entity_name,
                    "language": "en",
                    "type": "item",
                    "limit": 5,
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if resp.status_code == 429:
                _handle_429(attempt)
                continue
            if resp.status_code != 200:
                logger.warning(f"Wikidata search HTTP {resp.status_code} for '{entity_name}'")
                return None

            data = resp.json()
            results = data.get("search", [])
            if not results:
                return None

            top = results[0]
            return {
                "qid": top.get("id"),
                "label": top.get("label"),
                "description": top.get("description"),
            }
        except Exception as e:
            logger.warning(f"Wikidata search error for '{entity_name}': {e}")
            if attempt < 3:
                time.sleep(5)
    return None


def get_entity_p856(qid: str) -> Optional[str]:
    """Fetch the P856 (official website) claim for an entity."""
    for attempt in range(1, 4):
        try:
            resp = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": qid,
                    "props": "claims",
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if resp.status_code == 429:
                _handle_429(attempt)
                continue
            if resp.status_code != 200:
                return None

            data = resp.json()
            entity = data.get("entities", {}).get(qid, {})
            claims = entity.get("claims", {})
            p856 = claims.get("P856", [])
            if p856:
                snak = p856[0].get("mainsnak", {})
                return snak.get("datavalue", {}).get("value")
            return None
        except Exception as e:
            logger.warning(f"P856 fetch error for {qid}: {e}")
            if attempt < 3:
                time.sleep(5)
    return None


def get_entity_p31(qid: str) -> Optional[str]:
    """Fetch the P31 (instance of) label for an entity."""
    for attempt in range(1, 4):
        try:
            resp = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": qid,
                    "props": "claims",
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if resp.status_code == 429:
                _handle_429(attempt)
                continue
            if resp.status_code != 200:
                return None

            data = resp.json()
            entity = data.get("entities", {}).get(qid, {})
            claims = entity.get("claims", {})
            p31 = claims.get("P31", [])
            if not p31:
                return None

            # Get the QID of the instance-of class
            class_qid = p31[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            if not class_qid:
                return None

            # Fetch the label for that class
            resp2 = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": class_qid,
                    "props": "labels",
                    "languages": "en",
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if resp2.status_code == 200:
                d2 = resp2.json()
                labels = d2.get("entities", {}).get(class_qid, {}).get("labels", {})
                en_label = labels.get("en", {}).get("value")
                return en_label
            return class_qid  # Fallback: return the QID itself
        except Exception as e:
            logger.warning(f"P31 fetch error for {qid}: {e}")
            if attempt < 3:
                time.sleep(5)
    return None


def get_entity_location(qid: str) -> dict:
    """Fetch P17 (country) and P131 (city/admin) for an entity."""
    result = {"country": None, "city": None}
    for attempt in range(1, 4):
        try:
            resp = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": qid,
                    "props": "claims",
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if resp.status_code == 429:
                _handle_429(attempt)
                continue
            if resp.status_code != 200:
                return result

            data = resp.json()
            entity = data.get("entities", {}).get(qid, {})
            claims = entity.get("claims", {})

            # P17 = country
            p17 = claims.get("P17", [])
            if p17:
                country_qid = p17[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                if country_qid:
                    result["country"] = _get_label(country_qid)

            # P131 = located in administrative entity (often city)
            p131 = claims.get("P131", [])
            if p131:
                city_qid = p131[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                if city_qid:
                    result["city"] = _get_label(city_qid)

            return result
        except Exception as e:
            logger.warning(f"Location fetch error for {qid}: {e}")
            if attempt < 3:
                time.sleep(5)
    return result


def _get_label(qid: str) -> Optional[str]:
    """Fetch the English label for a QID."""
    try:
        resp = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels",
                "languages": "en",
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("entities", {}).get(qid, {}).get("labels", {}).get("en", {}).get("value")
    except Exception:
        pass
    return None


def fetch_wikipedia_summary(entity_name: str) -> Optional[str]:
    """Fetch page/summary extract from English Wikipedia."""
    encoded = quote(entity_name.strip().replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"

    for attempt in range(1, 4):
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
                timeout=15,
            )
            if resp.status_code == 429:
                _handle_429(attempt)
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.warning(f"Wikipedia summary HTTP {resp.status_code} for '{entity_name}'")
                return None

            data = resp.json()
            return data.get("extract", None)
        except Exception as e:
            logger.warning(f"Wikipedia summary error for '{entity_name}': {e}")
            if attempt < 3:
                time.sleep(5)
    return None


def fetch_wikipedia_summary_latency(entity_name: str) -> dict:
    """Fetch Wikipedia summary and measure latency."""
    encoded = quote(entity_name.strip().replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"

    start = time.perf_counter()
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=15,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "latency_ms": round(latency_ms, 1),
            "status": resp.status_code,
            "success": resp.status_code == 200,
        }
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return {"latency_ms": round(latency_ms, 1), "status": None, "success": False, "error": str(e)}


def harvest_single_entity(entity_name: str) -> dict:
    """Harvest complete ground truth for one entity from Wikimedia."""
    logger.info(f"Harvesting: {entity_name}")

    record = {
        "entity_name": entity_name,
        "qid": None,
        "label": None,
        "description": None,
        "wikipedia_extract": None,
        "official_website": None,
        "instance_of": None,
        "country": None,
        "city": None,
        "harvest_time": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Step 1: Search Wikidata
    wd = search_wikidata_entity(entity_name)
    if wd:
        record["qid"] = wd.get("qid")
        record["label"] = wd.get("label")
        record["description"] = wd.get("description")

    time.sleep(1.0)

    # Step 2: If we got a QID, fetch P856 and P31
    if record["qid"]:
        record["official_website"] = get_entity_p856(record["qid"])
        time.sleep(1.0)

        record["instance_of"] = get_entity_p31(record["qid"])
        time.sleep(1.0)

        location = get_entity_location(record["qid"])
        record["country"] = location.get("country")
        record["city"] = location.get("city")
        time.sleep(1.0)

    # Step 3: Fetch Wikipedia summary
    record["wikipedia_extract"] = fetch_wikipedia_summary(entity_name)
    time.sleep(1.0)

    return record


def harvest_all() -> list:
    """Harvest ground truth for all 40 entities."""
    all_entities = WELL_KNOWN_VENUES + LONG_TAIL_WORKS + FRENCH_ENTITIES
    assert len(all_entities) == 40, f"Expected 40 entities, got {len(all_entities)}"

    results = []
    for i, entity in enumerate(all_entities):
        logger.info(f"[{i+1}/40] Harvesting '{entity}'...")
        record = harvest_single_entity(entity)
        results.append(record)

        # Progress save every 5 entities
        if (i + 1) % 5 == 0:
            _save_fixture(results)
            logger.info(f"  Progress saved ({i+1}/40)")

    _save_fixture(results)
    return results


def _save_fixture(data: list):
    """Save the ground truth fixture to disk."""
    with open(FIXTURE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    print(f"Harvesting ground truth for 40 entities...")
    print(f"Output: {FIXTURE_PATH}")
    print(f"This will take ~5 minutes (rate-limited to 1 call/sec).")
    print()

    results = harvest_all()

    # Report
    found = sum(1 for r in results if r["qid"])
    wiki = sum(1 for r in results if r["wikipedia_extract"])
    p856 = sum(1 for r in results if r["official_website"])
    print(f"\nHarvest complete:")
    print(f"  Wikidata QID found: {found}/40")
    print(f"  Wikipedia extract:  {wiki}/40")
    print(f"  P856 website:       {p856}/40")
    print(f"\nSaved to: {FIXTURE_PATH}")
