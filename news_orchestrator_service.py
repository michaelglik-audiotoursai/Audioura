#!/usr/bin/env python3
"""
News Orchestrator Service - Coordinates article processing workflow
"""
import os
import sys
import psycopg2
from flask import Flask, request, jsonify, send_file as _send_file
import inspect as _inspect
import uuid
import hmac
import logging
import requests


def _compat_send_file(path_or_file, **kwargs):
    """Version-tolerant send_file wrapper.

    Flask <2.0 uses ``attachment_filename``; Flask >=2.0 renamed it to
    ``download_name``.  This helper accepts either and maps to whichever the
    installed Flask supports, so the same code runs on both.
    """
    sig = _inspect.signature(_send_file)
    params = sig.parameters

    download_name = kwargs.pop("download_name", None)
    attachment_filename = kwargs.pop("attachment_filename", None)
    name = download_name or attachment_filename

    if name:
        if "download_name" in params:
            kwargs["download_name"] = name
        else:
            kwargs["attachment_filename"] = name

    return _send_file(path_or_file, **kwargs)


send_file = _compat_send_file
from datetime import datetime
import io

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Force unbuffered output for real-time logs
import sys
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# Inter-service URLs (env-var-driven for Cloud Run, defaults for local Docker)
NEWS_GENERATOR_URL = os.getenv('NEWS_GENERATOR_URL', 'http://news-generator-1:5010')
NEWS_PROCESSOR_URL = os.getenv('NEWS_PROCESSOR_URL', 'http://news-processor-1:5011')
TRANSLATION_URL = os.getenv('TRANSLATION_URL', 'http://translation-service-1:5030')

# OIDC token cache for authenticated inter-service calls on Cloud Run
import time as _time
_token_cache = {}

def _get_auth_headers(target_url):
    """Get OIDC identity token for inter-service calls on Cloud Run.
    Returns empty dict locally (services are unauthenticated in Docker)."""
    if target_url.startswith('http://'):
        return {}  # Local Docker — no auth needed
    # Cloud Run: fetch identity token from metadata server
    audience = target_url.rstrip('/')
    cached = _token_cache.get(audience)
    if cached and cached['expires'] > _time.time():
        return {'Authorization': f"Bearer {cached['token']}"}
    metadata_url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={audience}"
    try:
        resp = requests.get(metadata_url, headers={"Metadata-Flavor": "Google"}, timeout=5)
        if resp.status_code == 200:
            token = resp.text
            _token_cache[audience] = {'token': token, 'expires': _time.time() + 3500}
            return {'Authorization': f"Bearer {token}"}
    except Exception as e:
        logging.error(f"[AUTH] Failed to get identity token for {audience}: {e}")
    return {}

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "news_orchestrator_1"})

@app.route('/generate-news', methods=['POST'])
def generate_news():
    try:
        data = request.get_json()
        article_text = data.get('article_text', '')
        request_string = data.get('request_string', 'News Article')
        secret_id = data.get('secret_id', 'anonymous')
        major_points_count = data.get('major_points_count', 0)
        
        if not article_text:
            return jsonify({"error": "Article text is required"}), 400
        
        # ── Caller identity verification ────────────────────────────────────
        # Determine if this is a trusted internal service (newsletter-processor).
        # Trust is established via X-Internal-Service header with a shared secret
        # that the gateway STRIPS from inbound client requests (cannot be spoofed).
        _INTERNAL_SERVICE_SECRET = os.getenv('INTERNAL_SERVICE_SECRET', '')
        caller_token = request.headers.get('X-Internal-Service', '')
        is_trusted_internal = (
            _INTERNAL_SERVICE_SECRET
            and caller_token
            and hmac.compare_digest(caller_token, _INTERNAL_SERVICE_SECRET)
        )
        
        if is_trusted_internal:
            # Trusted internal caller (newsletter-processor) — skip per-article quota.
            # The newsletter-processor does one batch-level quota check + debit upfront.
            logging.info(f"[QUOTA] Internal service call verified — skipping per-article quota (user={secret_id})")
            from entitlements import get_user_plan, words_budget_for_minutes
            try:
                plan = get_user_plan(secret_id)
                max_narration_words = words_budget_for_minutes(plan.get('news_max_minutes'))
            except Exception:
                max_narration_words = words_budget_for_minutes(10)  # fallback: 10 min cap
        else:
            # External caller (via gateway or direct) — full auth + quota enforcement.
            if not secret_id or secret_id == 'anonymous':
                logging.warning("[QUOTA] Missing/anonymous secret_id — denying news (fail-closed)")
                return jsonify({
                    "allowed": False, "error": "auth_required",
                    "message": "A valid user id is required to generate news."
                }), 401

            try:
                from entitlements import check_news_quota
                quota = check_news_quota(secret_id)
            except Exception as quota_err:
                logging.error(f"[QUOTA] News quota check failed — denying (fail-closed): {quota_err}")
                return jsonify({
                    "allowed": False, "error": "quota_check_failed",
                    "message": "Could not verify your news quota. Please try again."
                }), 503

            if not quota['allowed']:
                logging.info(f"[QUOTA] Denied news for {secret_id}: {quota}")
                return jsonify(quota), 429
            logging.info(f"[QUOTA] Allowed news for {secret_id}: used={quota['used']}, remaining={quota['remaining']}")

            # Derive word budget from news_max_minutes for narration length capping
            from entitlements import words_budget_for_minutes
            max_narration_words = words_budget_for_minutes(quota.get('news_max_minutes'))
        
        # Generate unique article ID
        article_id = str(uuid.uuid4())
        
        # ── NEWS CACHE CHECK ────────────────────────────────────────────────
        # Before paying for generation, check if identical content is already cached.
        # Cache key = SHA256(normalized_article_text | major_points_count).
        # Matches tour_cache_layer1 pattern: check → hit → meter at $0.00 → return.
        _cache_hit = False
        _cached_article_id = None
        try:
            _db_url = f"postgresql://{os.getenv('DB_USER', 'admin')}:{os.getenv('DB_PASSWORD', 'password123')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5433')}/{os.getenv('DB_NAME', 'audiotours')}"
            from news_cache_layer1 import get_cached_news
            _cache_result = get_cached_news(article_text, major_points_count, _db_url)
            if _cache_result is not None:
                _cached_article_id, _cached_audio = _cache_result
                _cache_hit = True
                logging.info(f"[NEWS_CACHE] HIT — reusing article_id={_cached_article_id} for request from {secret_id}")
        except Exception as _cache_err:
            # D14: instrumentation fails open — cache miss does not block generation
            logging.warning(f"[NEWS_CACHE] Check failed (proceeding without cache): {_cache_err}")
        
        if _cache_hit:
            # ── CACHE HIT PATH ──────────────────────────────────────────────
            # Meter at $0.00 with cache_hit=true, matching the tour path.
            try:
                from cost_meter import record_operation
                from cost_rates import CACHE_HIT_COST_USD
                record_operation(
                    operation_type="news_cache_hit",
                    our_cost_usd=CACHE_HIT_COST_USD,
                    cache_hit=True,
                    user_id=secret_id,
                    job_id=_cached_article_id,
                    breakdown={"tts": 0.0, "llm": 0.0, "source": "news_cache"},
                )
                logging.info(f"[COST_METER] CACHE_HIT | news_cache_hit | $0.00 | user={secret_id} | job={_cached_article_id}")
            except Exception as _meter_err:
                # D14: instrumentation fails open
                logging.warning(f"[NEWS_CACHE] Metering failed (non-fatal): {_meter_err}")

            # [LOCAL-201] Cache-hit charging (D45 extended): charge user same as fresh.
            # Basis comes from the original cost_ledger row. None → $0.00 (safe).
            # Idempotency key: charge:{user}:{article_id} — same as fresh path.
            # Retry of the same request with same article_id is a no-op in wallet.
            if secret_id and secret_id != 'anonymous' and not is_trusted_internal:
                try:
                    from cost_meter import lookup_fresh_cost_for_cache_hit as _lookup_basis
                    from pricing import compute_user_charge as _compute_charge
                    from wallet_ledger import charge as _wallet_charge
                    from entitlements import _get_subscription_tier

                    _fresh_basis = _lookup_basis(_cached_article_id, "news_cache_hit")
                    _charge_result = _compute_charge(
                        our_cost_usd=0.00,
                        cache_hit=True,
                        operation_type="news_cache_hit",
                        fresh_cost_usd=_fresh_basis,
                        description=f"Article: {request_string[:200] if 'request_string' in dir() else 'news'}",
                    )

                    _user_tier = _get_subscription_tier(secret_id)
                    if _user_tier == 'ppu' and _charge_result['user_charge_cents'] > 0:
                        _charge_idem_key = f"charge:{secret_id}:{_cached_article_id}"
                        _row_id, _new_bal, _was_stopped = _wallet_charge(
                            user_id=secret_id,
                            charge_usd=_charge_result['user_charge_usd'],
                            idempotency_key=_charge_idem_key,
                            description=_charge_result['description'] + f" — ${_charge_result['user_charge_usd']:.2f}",
                            job_id=_cached_article_id,
                        )
                        if _was_stopped:
                            logging.error(
                                f"[LOCAL-201] NEWS CACHE-HIT CHARGE BLOCKED (zero balance) for {secret_id} article={_cached_article_id}"
                            )
                            return jsonify({
                                "error": "insufficient_balance",
                                "message": "Insufficient balance. Please top up your credits.",
                            }), 402
                        logging.info(
                            f"[LOCAL-201] News cache-hit charged: ${_charge_result['user_charge_usd']:.2f} | "
                            f"basis=${_fresh_basis or 0:.4f} | balance={_new_bal}¢ | user={secret_id} | article={_cached_article_id}"
                        )
                    else:
                        logging.info(
                            f"[LOCAL-201] News cache-hit no charge: basis={_fresh_basis} | tier={_user_tier} | user={secret_id}"
                        )
                except Exception as _cache_charge_err:
                    # Cache-hit charging fails OPEN — content already exists, not new work.
                    logging.warning(f"[LOCAL-201] News cache-hit charging failed (non-fatal): {_cache_charge_err}")

            return jsonify({
                "status": "success",
                "article_id": _cached_article_id,
                "message": "News article served from cache",
                "cache_hit": True
            })
        # ── END CACHE CHECK ─────────────────────────────────────────────────
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # DEBUG: Log content before encoding
        logging.info(f"🔍 ORCHESTRATOR DEBUG: Storing article {article_id}")
        logging.info(f"🔍 Original article_text length: {len(article_text)} chars")
        logging.info(f"🔍 Article_text preview: {article_text[:200]}...")
        
        # Encode to UTF-8 bytes
        utf8_bytes = article_text.encode('utf-8')
        logging.info(f"🔍 UTF-8 encoded length: {len(utf8_bytes)} bytes")
        
        # Create article request
        cursor.execute("""
            INSERT INTO article_requests 
            (article_id, secret_id, request_string, article_text, status, created_at, started_at)
            VALUES (%s, %s, %s, %s, 'started', %s, %s)
        """, (article_id, secret_id, request_string, utf8_bytes, 
              datetime.now(), datetime.now()))
        
        # DEBUG: Verify what was stored
        cursor.execute("SELECT article_text FROM article_requests WHERE article_id = %s", (article_id,))
        stored_bytes = cursor.fetchone()[0]
        if hasattr(stored_bytes, 'tobytes'):
            stored_bytes = stored_bytes.tobytes()
        else:
            stored_bytes = bytes(stored_bytes)
        
        stored_text = stored_bytes.decode('utf-8')
        logging.info(f"🔍 Stored and retrieved length: {len(stored_text)} chars")
        logging.info(f"🔍 Storage integrity check: {stored_text == article_text}")
        logging.info(f"🔍 Retrieved preview: {stored_text[:200]}...")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Call news generator service
        logging.info(f"🔍 ORCHESTRATOR: About to call generator for {article_id}")
        logging.info(f'Calling news generator for article {article_id} with {major_points_count} major points')
        generator_response = requests.post(
            f'{NEWS_GENERATOR_URL}/process-article/{article_id}',
            json={'max_major_points': major_points_count, 'max_narration_words': max_narration_words},
            headers={**{'Content-Type': 'application/json'}, **_get_auth_headers(NEWS_GENERATOR_URL)},
            timeout=30
        )
        
        logging.info(f'Generator response: {generator_response.status_code}')
        if generator_response.status_code != 200:
            logging.error(f'Generator failed: {generator_response.text}')
            raise Exception(f"News generator failed: {generator_response.text}")
        
        # Call news processor service
        logging.info(f'Calling news processor for article {article_id}')
        processor_response = requests.post(
            f'{NEWS_PROCESSOR_URL}/process-audio/{article_id}',
            headers=_get_auth_headers(NEWS_PROCESSOR_URL),
            timeout=120
        )
        
        logging.info(f'Processor response: {processor_response.status_code}')
        if processor_response.status_code != 200:
            logging.error(f'Processor failed: {processor_response.text}')
            raise Exception(f"News processor failed: {processor_response.text}")
        
        logging.info(f'News generation completed successfully for {article_id}')
        
        # ── CACHE STORE ──────────────────────────────────────────────────────
        # Store the freshly generated article in the cache for future hits.
        try:
            _db_url = f"postgresql://{os.getenv('DB_USER', 'admin')}:{os.getenv('DB_PASSWORD', 'password123')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5433')}/{os.getenv('DB_NAME', 'audiotours')}"
            from news_cache_layer1 import store_news
            store_news(
                article_text=article_text,
                major_points_count=major_points_count,
                article_id=article_id,
                db_url=_db_url,
                request_string=request_string,
                content_length=len(article_text),
            )
        except Exception as _store_err:
            # D14: instrumentation fails open — cache store failure does not block response
            logging.warning(f"[NEWS_CACHE] Store failed (non-fatal): {_store_err}")
        # ── END CACHE STORE ─────────────────────────────────────────────────
        
        # ── [LOCAL-69] Meter news generation cost ───────────────────────────
        # Cost model (verified by code trace):
        #   - Polly TTS: multiple segments (summary, topics, per-topic, help, full article)
        #     All text passes through clean_text_for_polly() which truncates to 5000 chars/segment.
        #   - LLM (GPT-3.5-turbo): conditional short-title generation when title > 12 words
        #     via voice_control → voice_nlp_service → OpenAI API (~60 tokens max).
        #   - No search API cost (article text arrives pre-extracted).
        #
        # TTS character estimate: we know article_text length. The processor generates:
        #   audio_1 (summary ~200 chars), audio-topics (topics list ~300 chars),
        #   per-topic audios (N × ~300 chars), audio-help (fixed ~700 chars),
        #   audio-99 (full article, capped at 5000 chars by clean_text_for_polly).
        # Conservative estimate: min(article_text_chars * 1.2, 5000 + N*500 + 1200)
        # Simplification: use article_text length as the TTS input proxy.
        try:
            from cost_meter import record_operation
            from cost_rates import tts_cost, llm_cost, POLLY_COST_PER_CHAR

            # Use original request_string for Wallet display (before generator overwrites it).
            # Falls back to the generator's extracted title if request_string was generic.
            _display_title = request_string if request_string and request_string != 'News Article' else "News Article"

            # TTS cost: the processor sends cleaned text through Polly.
            # Each segment is capped at 5000 chars. Segments: summary, topics list,
            # N topic audios, help commands (~700 fixed), full article (capped 5000).
            # Best proxy: take the original article length (before cleaning removes ~20%),
            # cap at what Polly actually processes. Total TTS chars ≈ article_text * 1.5
            # (summary + topics + full article overlap). But full article is capped at 5000.
            _tts_chars = min(len(article_text), 5000) + 1200  # full article cap + overhead (summary + help)
            if major_points_count > 0:
                _tts_chars += major_points_count * 400  # topics list + per-topic audio
            _tts_cost = tts_cost(_tts_chars)

            # LLM cost: short title generation only fires when title > 12 words.
            # We check the original request_string — if the generator finds a longer
            # title, it may also trigger LLM, but we can't know until after processing.
            # Use article text word count as proxy for title length post-extraction.
            _title_words = len(_display_title.split()) if _display_title else 0
            _llm_cost = 0.0
            if _title_words > 12:
                # GPT-3.5-turbo, ~100 tokens prompt + ~60 tokens response
                _llm_cost = llm_cost(total_tokens=160)  # deprecated path; ~160 total tokens

            _total_cost = _tts_cost + _llm_cost
            _breakdown = {"tts": round(_tts_cost, 6), "llm": round(_llm_cost, 6)}

            # Human-readable description for Wallet display
            _description = f"Article: {_display_title[:200]}"

            record_operation(
                operation_type="news_generate",
                our_cost_usd=_total_cost,
                cache_hit=False,
                user_id=secret_id,
                job_id=article_id,
                breakdown=_breakdown,
                description=_description,
            )
            logging.info(
                f"[LOCAL-69] News cost metered: ${_total_cost:.6f} | "
                f"tts=${_tts_cost:.6f} ({_tts_chars} chars) | llm=${_llm_cost:.6f} | "
                f"article={article_id} | user={secret_id}"
            )
        except Exception as _meter_err:
            # Metering is instrumentation — fails open (D14 rule).
            logging.error(f"[LOCAL-69] News cost metering failed (non-fatal): {_meter_err}")
        # ── end metering ────────────────────────────────────────────────────

        # ── [LOCAL-83] Charge the user's wallet — SEPARATE try block, FAILS CLOSED.
        # This is a billing control (D14): if charging fails, do NOT deliver.
        # Do NOT share an exception handler with cost metering above.
        # Idempotency: use article_id as the key — a retried generation charges once.
        if secret_id and secret_id != 'anonymous' and not is_trusted_internal:
            try:
                from pricing import compute_user_charge as _compute_charge
                from wallet_ledger import charge as _wallet_charge, record_unlimited_cost as _record_unlimited
                from entitlements import _get_subscription_tier

                _user_tier = _get_subscription_tier(secret_id)

                # Reuse _total_cost from metering above (or default 0 if metering failed)
                _news_cost = _total_cost if '_total_cost' in dir() else 0.0

                _charge_result = _compute_charge(
                    our_cost_usd=_news_cost,
                    cache_hit=False,
                    operation_type="news_generate",
                    description=_description if '_description' in dir() else f"Article: {request_string[:200]}",
                )

                if _user_tier == 'ppu' and _charge_result['user_charge_cents'] > 0:
                    _charge_idem_key = f"charge:{secret_id}:{article_id}"
                    _row_id, _new_bal, _was_stopped = _wallet_charge(
                        user_id=secret_id,
                        charge_usd=_charge_result['user_charge_usd'],
                        idempotency_key=_charge_idem_key,
                        description=f"Article: {request_string[:200]} — ${_charge_result['user_charge_usd']:.2f}",
                        job_id=article_id,
                    )
                    if _was_stopped:
                        logging.error(
                            f"[LOCAL-83] CHARGE BLOCKED (zero balance) for {secret_id} article={article_id}"
                        )
                        return jsonify({
                            "error": "insufficient_balance",
                            "message": "Insufficient balance to complete this article. Please top up your credits.",
                        }), 402

                    logging.info(
                        f"[LOCAL-83] PPU charged: ${_charge_result['user_charge_usd']:.2f} | "
                        f"balance={_new_bal}¢ | user={secret_id} | article={article_id}"
                    )

                elif _user_tier == 'unlimited':
                    from decimal import Decimal as _Dec
                    _record_unlimited(secret_id, _Dec(str(_news_cost)))
                    logging.info(
                        f"[LOCAL-83] Unlimited cost recorded: ${_news_cost:.6f} | user={secret_id} | article={article_id}"
                    )

                # free tier: no wallet action needed
            except Exception as _charge_err:
                # FAIL CLOSED (D14): charging failed — do NOT deliver unbilled article.
                logging.error(
                    f"[LOCAL-83] CHARGING FAILED — aborting news delivery (fail-closed): {_charge_err}"
                )
                return jsonify({
                    "error": "billing_unavailable",
                    "message": f"Billing unavailable ({type(_charge_err).__name__}). Article not delivered.",
                }), 503
        # ── end charging ────────────────────────────────────────────────────

        return jsonify({
            "status": "success",
            "article_id": article_id,
            "message": "News article processed successfully",
            "cache_hit": False
        })
        
    except Exception as e:
        logging.error(f"Error in news orchestration: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/download/<article_id>', methods=['GET'])
def download_news(article_id):
    try:
        # Get language parameter from query string
        language = request.args.get('language', 'en')
        
        # Validate language parameter
        supported_languages = ['en', 'ru', 'es', 'fr', 'de', 'zh', 'ko']
        if language not in supported_languages:
            return jsonify({"error": f"Unsupported language: {language}. Supported: {supported_languages}"}), 400
        
        logging.info(f"Download request for article {article_id} in language: {language}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # If non-English language requested, check for existing translation or create one
        final_article_id = article_id
        if language != 'en':
            logging.info(f"Non-English language requested: {language}")
            
            # Check if translation already exists
            cursor.execute(
                "SELECT article_id FROM article_requests WHERE original_article_id = %s AND content_language = %s",
                (article_id, language)
            )
            existing_translation = cursor.fetchone()
            
            if existing_translation:
                final_article_id = existing_translation[0]
                logging.info(f"Found existing {language} translation: {final_article_id}")
            else:
                # Create translation using translation service
                try:
                    translation_data = {
                        "content_id": article_id,
                        "content_type": "article",
                        "languages": [language]
                    }
                    
                    logging.info(f"Calling translation service for article {article_id} -> {language}")
                    translation_response = requests.post(
                        f"{TRANSLATION_URL}/translate-with-audio",
                        headers={**{"Content-Type": "application/json"}, **_get_auth_headers(TRANSLATION_URL)},
                        json=translation_data,
                        timeout=120
                    )
                    
                    if translation_response.status_code == 200:
                        translation_result = translation_response.json()
                        # Fix: Use correct field name from translation service response
                        translation_info = translation_result.get('translations', {}).get(language, {})
                        translated_article_id = translation_info.get('id')
                        
                        if translated_article_id:
                            final_article_id = translated_article_id
                            logging.info(f"Translation successful! Using translated article: {final_article_id}")
                        else:
                            logging.warning(f"Translation completed but no article ID returned, using English version")
                    else:
                        logging.error(f"Translation failed: {translation_response.status_code} - {translation_response.text}")
                        logging.info(f"Falling back to English version")
                        
                except Exception as translation_error:
                    logging.error(f"Translation error: {translation_error}")
                    logging.info(f"Falling back to English version")
        cursor.execute("""
            SELECT ar.subscription_required, ar.subscription_domain, ar.request_string
            FROM article_requests ar
            WHERE ar.article_id = %s
        """, (article_id,))
        
        subscription_info = cursor.fetchone()
        if not subscription_info:
            cursor.close()
            conn.close()
            return jsonify({"error": "Article not found"}), 404
        
        subscription_required, subscription_domain, article_title = subscription_info
        
        # CRITICAL SECURITY CHECK: Validate subscription credentials if required
        if subscription_required and subscription_domain:
            # Get user_id from request parameters or headers
            user_id = request.args.get('user_id') or request.headers.get('X-User-ID')
            
            if not user_id:
                cursor.close()
                conn.close()
                logging.warning(f"SECURITY BLOCK: No user_id provided for subscription article {article_id}")
                return jsonify({
                    "error": "Subscription required",
                    "message": f"This article requires a subscription to {subscription_domain}. Please provide credentials.",
                    "subscription_domain": subscription_domain,
                    "article_title": article_title
                }), 403
            
            # Check if user has VERIFIED credentials for this domain
            cursor.execute("""
                SELECT 1 FROM user_subscription_credentials 
                WHERE device_id = %s AND domain = %s AND verified_at IS NOT NULL
            """, (user_id, subscription_domain))
            
            has_verified_credentials = cursor.fetchone() is not None
            
            if not has_verified_credentials:
                cursor.close()
                conn.close()
                logging.warning(f"SECURITY BLOCK: User {user_id} has no verified credentials for {subscription_domain} - article {article_id}")
                return jsonify({
                    "error": "Subscription required",
                    "message": f"This article requires verified credentials for {subscription_domain}. Please submit valid subscription credentials.",
                    "subscription_domain": subscription_domain,
                    "article_title": article_title
                }), 403
            
            logging.info(f"SECURITY PASS: User {user_id} has verified credentials for {subscription_domain} - allowing access to article {article_id}")
        
        # Get news article from database (use final_article_id which may be translated)
        cursor.execute("""
            SELECT news_article, article_name, article_type 
            FROM news_audios 
            WHERE article_id = %s
        """, (final_article_id,))
        
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({"error": "News article not found"}), 404
        
        news_article, article_name, article_type = result
        article_type = article_type or 'Others'
        
        cursor.close()
        conn.close()
        
        # Return ZIP file (use final_article_id for filename to distinguish translations)
        return send_file(
            io.BytesIO(news_article),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{final_article_id}.zip'
        )
        
    except Exception as e:
        logging.error(f"Error downloading news {article_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/status/<article_id>', methods=['GET'])
def get_status(article_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT status, created_at, started_at, finished_at, request_string
            FROM article_requests 
            WHERE article_id = %s
        """, (article_id,))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "Article not found"}), 404
        
        status, created_at, started_at, finished_at, request_string = result
        
        cursor.close()
        conn.close()
        
        # Map status for mobile app compatibility
        mobile_status = 'completed' if status == 'finished' else status
        
        return jsonify({
            "status": mobile_status,
            "article_id": article_id,
            "request_string": request_string,
            "created_at": created_at.isoformat() if created_at else None,
            "started_at": started_at.isoformat() if started_at else None,
            "finished_at": finished_at.isoformat() if finished_at else None,
            "progress": get_progress_message(status)
        })
        
    except Exception as e:
        logging.error(f"Error getting status for {article_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

def get_progress_message(status):
    messages = {
        'started': 'Processing article text...',
        'ready': 'Converting to audio...',
        'finished': 'Article ready for download!',
        'error': 'Processing failed'
    }
    return messages.get(status, 'Unknown status')

@app.route('/articles', methods=['GET'])
def get_articles():
    """Get all available articles with types for mobile app"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get articles that are finished and have audio
        cursor.execute("""
            SELECT na.article_id, na.article_name, na.article_type, na.created_at,
                   ar.request_string
            FROM news_audios na
            JOIN article_requests ar ON na.article_id = ar.article_id
            WHERE ar.status = 'finished'
            ORDER BY na.created_at DESC
            LIMIT 50
        """)
        
        results = cursor.fetchall()
        articles = []
        
        for result in results:
            article_id, article_name, article_type, created_at, request_string = result
            articles.append({
                'article_id': article_id,
                'title': article_name or request_string,
                'article_type': article_type or 'Others',
                'created_at': created_at.isoformat() if created_at else None
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'articles': articles,
            'total': len(articles)
        })
        
    except Exception as e:
        logging.error(f"Error getting articles: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5012')), debug=False)