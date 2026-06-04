"""
API Call Chain Logger
Logs every internal service-to-service call and every OpenAI call in a numbered sequential chain.
Usage: import api_call_logger; api_call_logger.log(step, data)
"""
import os
import json
import threading
from datetime import datetime

_lock = threading.Lock()
_call_number = 0
_log_file = None

def _get_log_file():
    global _log_file
    if _log_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _log_file = f"/app/api_call_chain_{timestamp}.txt"
    return _log_file

def log(step_name, data: dict):
    """Log a single step in the API call chain."""
    global _call_number
    with _lock:
        _call_number += 1
        call_num = _call_number
    
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    lines = [
        f"\n{'='*70}",
        f"CALL #{call_num:03d} | {timestamp} | {step_name}",
        f"{'='*70}",
    ]
    
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            lines.append(f"  {key}:")
            try:
                formatted = json.dumps(value, indent=4, ensure_ascii=False)
                for line in formatted.splitlines():
                    lines.append(f"    {line}")
            except Exception:
                lines.append(f"    {str(value)[:500]}")
        else:
            val_str = str(value)
            if len(val_str) > 2000:
                val_str = val_str[:2000] + f"\n    ... [TRUNCATED - total {len(str(value))} chars]"
            lines.append(f"  {key}: {val_str}")
    
    output = "\n".join(lines) + "\n"
    
    log_path = _get_log_file()
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(output)
    except Exception as e:
        print(f"[api_call_logger] Failed to write log: {e}")
    
    # Also print to stdout so it appears in docker logs
    print(output)
    return call_num

def log_openai_call(prompt: str, total_stops, response_text: str, status_code: int):
    """Specialized logger for OpenAI calls - highlights the key fields."""
    stop_count_in_prompt = str(total_stops) in prompt if total_stops else False
    
    # Count stops in response
    import re
    stops_in_response = re.findall(r'Stop \d+:', response_text)
    
    return log("OPENAI_API_CALL", {
        "total_stops_requested": total_stops,
        "stop_count_in_prompt": stop_count_in_prompt,
        "http_status": status_code,
        "prompt_first_500_chars": prompt[:500],
        "prompt_last_300_chars": prompt[-300:] if len(prompt) > 300 else "(same as above)",
        "stops_found_in_response": len(stops_in_response),
        "stop_markers_in_response": stops_in_response,
        "response_first_500_chars": response_text[:500],
    })

def get_log_path():
    return _get_log_file()
