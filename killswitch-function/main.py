"""
Billing Kill-Switch Cloud Function
====================================
Triggered by Pub/Sub topic: projects/audiotours-migration/topics/billing-killswitch
When budget exceeds 100%, throttles all cost-bearing Cloud Run services to maxScale=1
(with minScale=0, so they scale to zero when idle — effectively disabled).
"""
import base64
import json
import functions_framework


PROJECT = "audiotours-migration"
REGION = "us-central1"
COST_SERVICES = [
    "tour-orchestrator",
    "tour-generator",
    "news-orchestrator",
    "news-generator",
    "news-processor",
    "translation-service",
    "polly-tts",
    "tour-worker",
]


@functions_framework.http
def killswitch(request):
    """Cloud Function entry point (HTTP-triggered by Eventarc/Pub/Sub push)."""
    
    # Parse the Cloud Event / Pub/Sub push envelope
    envelope = request.get_json(silent=True) or {}
    
    # Extract Pub/Sub message data — Gen2 functions receive CloudEvents
    message_data = '{}'
    
    # Try CloudEvent format (Gen2)
    if 'message' in envelope:
        raw = envelope['message'].get('data', '')
        if raw:
            try:
                message_data = base64.b64decode(raw).decode('utf-8')
            except Exception:
                message_data = raw
    elif 'data' in envelope:
        raw = envelope['data']
        if isinstance(raw, str):
            try:
                message_data = base64.b64decode(raw).decode('utf-8')
            except Exception:
                message_data = raw
        elif isinstance(raw, dict):
            message_data = json.dumps(raw)
    
    # Last resort: try the entire body as the message
    if message_data == '{}' and envelope:
        message_data = json.dumps(envelope)
    
    print(f"[KILLSWITCH] Raw envelope keys: {list(envelope.keys())}")
    print(f"[KILLSWITCH] Decoded message: {message_data[:200]}")
    
    try:
        budget_data = json.loads(message_data)
    except json.JSONDecodeError:
        # Handle malformed JSON (e.g. unquoted keys from shell quoting issues)
        # Try to extract key values with regex as fallback
        import re
        budget_data = {}
        for key in ['costAmount', 'budgetAmount', 'alertThresholdExceeded']:
            match = re.search(rf'{key}\s*[:\s]\s*([\d.]+)', message_data)
            if match:
                budget_data[key] = float(match.group(1))
        print(f"[KILLSWITCH] Parsed via regex fallback: {budget_data}")
    
    cost_amount = budget_data.get('costAmount', 0)
    budget_amount = budget_data.get('budgetAmount', 0)
    alert_threshold = budget_data.get('alertThresholdExceeded', 0)
    
    print(f"[KILLSWITCH] Cost: ${cost_amount}, Budget: ${budget_amount}, Threshold: {alert_threshold}")
    
    if alert_threshold < 1.0 and (not budget_amount or cost_amount < budget_amount):
        msg = f"Below 100% threshold ({alert_threshold*100}%) — no action"
        print(f"[KILLSWITCH] {msg}")
        return msg, 200
    
    print(f"[KILLSWITCH] 🚨 BUDGET EXCEEDED — throttling cost-bearing services to maxScale=1 (scale-to-zero idle)")
    
    # Use Cloud Run v1 API (Knative-compatible) to set maxScale annotation
    import google.auth
    import google.auth.transport.requests as google_requests
    import requests as http_requests
    
    credentials, _ = google.auth.default()
    auth_req = google_requests.Request()
    credentials.refresh(auth_req)
    
    results = []
    for svc in COST_SERVICES:
        try:
            # v1 API: get the service, patch the maxScale annotation
            url = f"https://{REGION}-run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{PROJECT}/services/{svc}"
            headers = {"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"}
            
            get_resp = http_requests.get(url, headers=headers, timeout=30)
            if get_resp.status_code != 200:
                print(f"[KILLSWITCH] ❌ {svc}: GET failed ({get_resp.status_code})")
                results.append(f"{svc}: FAILED (get)")
                continue
            
            service_data = get_resp.json()
            
            # Set maxScale annotation to 0
            if 'template' not in service_data['spec']:
                service_data['spec']['template'] = {}
            if 'metadata' not in service_data['spec']['template']:
                service_data['spec']['template']['metadata'] = {}
            if 'annotations' not in service_data['spec']['template']['metadata']:
                service_data['spec']['template']['metadata']['annotations'] = {}
            
            service_data['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/maxScale'] = '1'
            service_data['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/minScale'] = '0'
            
            # Update the service via PUT (v1 uses PUT, not PATCH)
            put_resp = http_requests.put(url, headers=headers, json=service_data, timeout=60)
            if put_resp.status_code in (200, 201):
                print(f"[KILLSWITCH] ✅ {svc} → throttled to maxScale=1 (scale-to-zero idle)")
                results.append(f"{svc}: disabled")
            else:
                err_text = put_resp.text[:100] if put_resp.text else "no body"
                print(f"[KILLSWITCH] ❌ {svc}: PUT failed ({put_resp.status_code}: {err_text})")
                results.append(f"{svc}: FAILED (put {put_resp.status_code})")
                
        except Exception as e:
            print(f"[KILLSWITCH] ❌ {svc}: {str(e)[:80]}")
            results.append(f"{svc}: ERROR")
    
    disabled = len([r for r in results if 'disabled' in r])
    summary = f"Kill-switch activated: {disabled}/{len(COST_SERVICES)} services throttled to maxScale=1"
    print(f"[KILLSWITCH] {summary}")
    return summary, 200
