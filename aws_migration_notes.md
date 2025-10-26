# AWS Migration Notes

## Current Setup
- Local Docker containers for API and database
- Standalone API for tour status updates
- Mobile app connecting to API endpoints

## AWS Migration Plan

### 1. Database Migration
- Migrate PostgreSQL to Amazon RDS
- Update connection parameters in API services

### 2. API Migration
- Deploy API services to AWS ECS or Lambda
- Create API Gateway endpoints for mobile app
- Implement proper authentication

### 3. Mobile App Updates
- Update API endpoints to point to AWS services
- Implement proper error handling for cloud environment
- Add retry logic for network issues

## Implementation Steps for AWS

1. Create RDS PostgreSQL instance
2. Migrate schema and data to RDS
3. Create Lambda functions for API endpoints:
   - `/update_tour` for tour status updates
   - `/sql` for direct SQL execution (with proper security)
4. Set up API Gateway to expose endpoints
5. Update mobile app configuration
6. Deploy and test

## Security Considerations
- Implement proper IAM roles for Lambda functions
- Use API keys for API Gateway
- Encrypt sensitive data in transit and at rest
- Implement proper input validation

## Monitoring and Logging
- Set up CloudWatch for monitoring
- Implement structured logging
- Create alerts for API failures