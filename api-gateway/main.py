"""
Audioura API Gateway — Python auth-proxy (replaces nginx)
Routes requests to backend Cloud Run services with Google identity tokens.
Backends set to --no-allow-unauthenticated; only this gateway is public.
"""
import os
import json
import time
import requests as http_requests
from flask import Flask, request, jsonify, Response
from functools import lru_cache

app = Flask(__name__)

# Backend service URLs
BACKENDS = {
    'map-delivery': os.getenv('MAP_DELIVERY_URL', 'https://map-delivery-60899077572.us-central1.run.app'),
    'orchestrator': os.getenv('ORCHESTRATOR_URL', 'https://tour-orchestrator-60899077572.us-central1.run.app'),
    'translation': os.getenv('TRANSLATION_URL', 'https://translation-service-60899077572.us-central1.run.app'),
    'news-orchestrator': os.getenv('NEWS_ORCHESTRATOR_URL', 'https://news-orchestrator-60899077572.us-central1.run.app'),
    'newsletter': os.getenv('NEWSLETTER_URL', 'https://newsletter-processor-60899077572.us-central1.run.app'),
}

# API key for cost-bearing endpoints (generation, translation, newsletter processing)
# Mobile app must send this in X-API-Key header to access these endpoints
API_KEY = os.getenv('GATEWAY_API_KEY', '')

def require_api_key():
    """Check X-API-Key header on cost-bearing endpoints. Returns error response or None."""
    if not API_KEY:
        return None  # No key configured = open (dev mode)
    client_key = request.headers.get('X-API-Key', '')
    if client_key != API_KEY:
        return jsonify({"error": "unauthorized", "message": "Valid X-API-Key header required"}), 401
    return None

# Token cache (tokens last ~1 hour)
_token_cache = {}

def get_identity_token(audience):
    """Fetch a Google-signed identity token from the metadata server."""
    cached = _token_cache.get(audience)
    if cached and cached['expires'] > time.time():
        return cached['token']
    
    # On Cloud Run, the metadata server provides identity tokens
    metadata_url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={audience}"
    try:
        resp = http_requests.get(metadata_url, headers={"Metadata-Flavor": "Google"}, timeout=5)
        if resp.status_code == 200:
            token = resp.text
            _token_cache[audience] = {'token': token, 'expires': time.time() + 3500}
            return token
    except Exception as e:
        print(f"[AUTH] Failed to get token for {audience}: {e}")
    return None


def proxy_request(backend_url, path, timeout=60):
    """Proxy the current Flask request to a backend with an identity token."""
    target_url = f"{backend_url}{path}"
    token = get_identity_token(backend_url)
    
    headers = {k: v for k, v in request.headers if k.lower() not in ('host', 'content-length', 'transfer-encoding')}
    if token:
        headers['Authorization'] = f"Bearer {token}"
    
    try:
        resp = http_requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            params=request.args,
            timeout=timeout,
            stream=True
        )
        
        excluded_headers = ('content-encoding', 'content-length', 'transfer-encoding', 'connection')
        response_headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded_headers]
        
        return Response(resp.content, status=resp.status_code, headers=response_headers)
    except http_requests.Timeout:
        return jsonify({"error": "Backend timeout"}), 504
    except Exception as e:
        return jsonify({"error": f"Proxy error: {str(e)}"}), 502


# === Health ===
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "api-gateway", "auth": "enabled"})


# === MAP DELIVERY ===
@app.route('/tours-near/<path:subpath>', methods=['GET'])
def tours_near(subpath):
    return proxy_request(BACKENDS['map-delivery'], f'/tours-near/{subpath}')

@app.route('/download-tour/<tour_id>', methods=['GET'])
def download_tour(tour_id):
    return proxy_request(BACKENDS['map-delivery'], f'/download-tour/{tour_id}', timeout=30)

@app.route('/tour/<tour_id>/resolve', methods=['GET'])
def resolve_tour(tour_id):
    return proxy_request(BACKENDS['map-delivery'], f'/tour/{tour_id}/resolve')

@app.route('/search-tours', methods=['GET', 'POST'])
def search_tours():
    return proxy_request(BACKENDS['map-delivery'], '/search-tours')


# === TOUR ORCHESTRATOR (COST-BEARING: require API key) ===
@app.route('/generate-complete-tour', methods=['POST'])
def generate_tour():
    auth_err = require_api_key()
    if auth_err:
        return auth_err
    return proxy_request(BACKENDS['orchestrator'], '/generate-complete-tour', timeout=600)

@app.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    return proxy_request(BACKENDS['orchestrator'], f'/status/{job_id}')

@app.route('/download/<job_id>', methods=['GET'])
def download_job(job_id):
    return proxy_request(BACKENDS['orchestrator'], f'/download/{job_id}', timeout=120)

@app.route('/tour-status', methods=['POST'])
def tour_status():
    auth_err = require_api_key()
    if auth_err:
        return auth_err
    return proxy_request(BACKENDS['orchestrator'], '/tour-status')

@app.route('/jobs', methods=['GET'])
def list_jobs():
    return proxy_request(BACKENDS['orchestrator'], '/jobs')


# === TRANSLATION (COST-BEARING: require API key) ===
@app.route('/translate-with-audio', methods=['POST'])
def translate():
    auth_err = require_api_key()
    if auth_err:
        return auth_err
    return proxy_request(BACKENDS['translation'], '/translate-with-audio', timeout=300)


# === NEWS/NEWSLETTER (COST-BEARING: require API key) ===
@app.route('/process_newsletter', methods=['POST'])
def process_newsletter():
    auth_err = require_api_key()
    if auth_err:
        return auth_err
    return proxy_request(BACKENDS['newsletter'], '/process_newsletter', timeout=120)

@app.route('/newsletters_v2', methods=['GET'])
def newsletters_v2():
    return proxy_request(BACKENDS['newsletter'], '/newsletters_v2')

@app.route('/get_articles_by_newsletter_id', methods=['GET'])
def get_articles():
    return proxy_request(BACKENDS['newsletter'], '/get_articles_by_newsletter_id')

@app.route('/news-download/<article_id>', methods=['GET'])
def download_article(article_id):
    return proxy_request(BACKENDS['news-orchestrator'], f'/download/{article_id}', timeout=30)


# === USER SYNC (stub) ===
@app.route('/sync', methods=['POST', 'GET'])
def sync():
    return jsonify({"status": "success"})


# === CATCH-ALL 404 ===
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "endpoint not found", "service": "api-gateway"}), 404


if __name__ == '__main__':
    port = int(os.getenv('PORT', '8080'))
    app.run(host='0.0.0.0', port=port, debug=False)
