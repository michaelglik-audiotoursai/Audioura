# Version Management System

## Critical Rule: Mobile-Service Version Alignment
**NEVER deploy mobile app without updating service versions to match!**

## Version Update Sequence
**ALWAYS follow this exact order for ANY change:**

### 1. Update Mobile Version
```yaml
# In pubspec.yaml
version: 1.1.0+[BUILD_NUMBER]  # Increment build number
```

### 2. Update Service Versions
```python
# In ALL modified service files
SERVICE_VERSION = "1.1.0.[BUILD_NUMBER]"  # Match mobile version
```

### 3. Commit with Version Tag
```bash
git add [all_modified_files]
git commit -m "v1.1.0.[BUILD_NUMBER] - [Description]"
git tag "v1.1.0.[BUILD_NUMBER]"
git push origin master --tags
```

### 4. Deploy Services
```bash
docker cp [service_file] [container]:/app/[service_file]
docker restart [container]
```

## Reproduction Commands
**To reproduce any version behavior:**
```bash
# Checkout specific version
git checkout v1.1.0.[BUILD_NUMBER]

# Rebuild services with that version's code
docker-compose down
docker-compose up --build

# Install corresponding APK from GitHub releases
```

## Files Requiring Version Updates
- `audio_tour_app/pubspec.yaml` (mobile version)
- `tour_generation_service.py` (service version)
- Any other modified service files

## Git Commit Format
- Format: `"v[VERSION] - [Description]"`
- Example: `"v1.1.0.167 - Fix ClassNotFoundException - correct MainActivity package"`

## Version Tracking Benefits
- Any mobile app version can be reproduced with matching services
- Clear audit trail of changes
- Rollback capability to any previous version
- Service-mobile compatibility guaranteed