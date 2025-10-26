#!/usr/bin/env python3
import sys
sys.path.append('/app')
from app import app

print("=== Flask Routes ===")
for rule in app.url_map.iter_rules():
    print(f"{rule.rule} -> {rule.endpoint} ({rule.methods})")