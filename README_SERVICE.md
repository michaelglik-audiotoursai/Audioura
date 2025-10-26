# Tour Generation REST API Service

A REST API service for generating audio tour text using OpenAI API, deployable with Docker.

## Features

- **Asynchronous Processing**: Tours are generated in background threads
- **Job Tracking**: Monitor generation progress with job IDs
- **File Storage**: Generated tours are stored persistently
- **Docker Ready**: Easy deployment with Docker Compose
- **Health Checks**: Built-in health monitoring
- **CORS Enabled**: Can be called from web applications

## API Endpoints

### Health Check
```
GET /health
```
Returns service health status and OpenAI configuration.

### Generate Tour
```
POST /generate
Content-Type: application/json

{
  "location": "deCordova Sculpture Park in Lincoln, MA",
  "tour_type": "sculpture",
  "total_stops": 10
}
```
Returns: `{"job_id": "uuid", "status": "queued"}`

### Check Job Status
```
GET /status/{job_id}
```
Returns job progress and completion status.

### Download Tour
```
GET /download/{job_id}
```
Downloads the generated tour text file.

### List Tours
```
GET /tours
```
Lists all generated tour files.

## Deployment

### Using Docker Compose (Recommended)

1. **Set Environment Variable**:
   ```bash
   export OPENAI_API_KEY="your-openai-api-key"
   ```

2. **Start Service**:
   ```bash
   docker-compose up -d
   ```

3. **Check Status**:
   ```bash
   curl http://localhost:5000/health
   ```

### Using Docker

1. **Build Image**:
   ```bash
   docker build -t tour-generator .
   ```

2. **Run Container**:
   ```bash
   docker run -d \
     -p 5000:5000 \
     -e OPENAI_API_KEY="your-key" \
     -v $(pwd)/tours:/app/tours \
     tour-generator
   ```

## Usage Examples

### Generate a Tour
```bash
curl -X POST http://localhost:5000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Museum of Fine Arts",
    "tour_type": "painting",
    "total_stops": 8
  }'
```

### Check Progress
```bash
curl http://localhost:5000/status/your-job-id
```

### Download Result
```bash
curl -O http://localhost:5000/download/your-job-id
```

## Storage

- **Current**: File system storage in `/app/tours` directory
- **Persistent**: Tours directory is mounted as Docker volume
- **Alternative Options**:
  - **PostgreSQL**: For structured data and metadata
  - **MongoDB**: For document-based storage
  - **Redis**: For caching and job queues
  - **AWS S3**: For cloud storage

## Configuration

- **OPENAI_API_KEY**: Required environment variable
- **Port**: Service runs on port 5000
- **Storage**: Tours saved to `/app/tours` directory
- **Limits**: 1-50 stops per tour

## Monitoring

- Health endpoint: `/health`
- Job status tracking
- Error handling and reporting
- Docker health checks included

## Development

Run locally:
```bash
export OPENAI_API_KEY="your-key"
python generate_tour_text_service.py
```

## Production Considerations

- Use environment-specific API keys
- Implement rate limiting
- Add authentication/authorization
- Set up log aggregation
- Monitor API costs
- Consider database storage for metadata
- Implement job cleanup for old tours