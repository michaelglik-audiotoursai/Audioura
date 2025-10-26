# Parallel Development Setup

## Problem Solved
- Frontend developer can work without waiting for backend implementation
- Backend developer can work without breaking frontend
- Both developers can work simultaneously on different features

## Architecture Changes

### 1. API Contract First
- `api-contracts/tour-api.yaml` defines the interface
- Both teams work against this contract
- Changes require agreement from both teams

### 2. Mock Server
- `mock-server/` provides fake API responses
- Frontend can develop against predictable data
- Run with: `docker-compose -f docker-compose.dev.yml up mock-server`

### 3. Environment Switching
- Flutter app can switch between mock and real APIs
- Use `ApiConfig.useMockServer(false)` to switch to real backend

## Development Workflows

### Frontend Developer
```bash
# Start only mock server
docker-compose -f docker-compose.dev.yml up mock-server

# In Flutter app, ensure mock mode is enabled
ApiConfig.useMockServer(true);
```

### Backend Developer
```bash
# Start full services
docker-compose -f docker-compose.dev.yml --profile full up

# Test against real APIs
ApiConfig.useMockServer(false);
```

### Integration Testing
```bash
# Start everything
docker-compose -f docker-compose.dev.yml --profile full up
```

## Benefits
- ✅ No more "implement backend first" blocking
- ✅ Parallel feature development
- ✅ Predictable frontend testing
- ✅ Easy environment switching
- ✅ Contract-driven development