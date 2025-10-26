# Docker Services Subsystem

## Service Architecture

### Tour Services
- `tour_orchestrator_service.py` - Main tour orchestration
- `generate_tour_text_service.py` - Tour text generation  
- `tour_generation_service.py` - Tour processing

### News Services
- `news_orchestrator_service.py` - News orchestration (container: news-orchestrator-1)
- `news_generator_service.py` - News text generation (container: news-generator-1)
- `news_processor_service.py` - News audio processing (container: news-processor-1)

## Deployment Commands

### Standard Deployment
```bash
# Copy file to container
docker cp service_file.py container-name:/app/service_file.py

# Restart container
docker restart container-name
```

### News Services Deployment
```bash
docker cp news_generator_service.py news-generator-1:/app/news_generator_service.py
docker cp news_processor_service.py news-processor-1:/app/news_processor_service.py
docker restart news-generator-1
docker restart news-processor-1
```

## Container Management

### Safe Operations
- Use `docker-compose stop` and `docker-compose start`
- AVOID `docker-compose down` (loses container state)
- NEVER use `docker-compose down -v` (deletes volumes)

### Database Operations
```bash
# Backup database
docker exec -t development-postgres-2-1 pg_dump -U admin audiotours > backup.sql

# Check container logs
docker logs container-name

# Check container status
docker ps
```

## Service Version Tracking
- Each service contains `SERVICE_VERSION = "1.1.0.X"`
- Health endpoints return version info
- Version must match mobile app version

## Key Dockerfiles
- `Dockerfile` - Main service
- `Dockerfile.orchestrator` - Tour orchestrator
- `Dockerfile.news-generator` - News generator
- `Dockerfile.news-orchestrator` - News orchestrator
- `Dockerfile.news-processor` - News processor