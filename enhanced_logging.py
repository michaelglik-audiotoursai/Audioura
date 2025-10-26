#!/usr/bin/env python3
"""
Enhanced logging for tour_orchestrator_service.py
"""
import logging
import sys
import os
import datetime

# Configure logging
def setup_logging():
    """Set up enhanced logging for the tour orchestrator service."""
    # Create logs directory if it doesn't exist
    logs_dir = "/app/logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # Set up file handler
    log_file = os.path.join(logs_dir, f"tour_orchestrator_{datetime.datetime.now().strftime('%Y%m%d')}.log")
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Log startup message
    logging.info("Enhanced logging initialized")
    return logging.getLogger()

# Create logger
logger = setup_logging()

def log_request(request):
    """Log details of an incoming request."""
    logger.info(f"=== INCOMING REQUEST: {request.method} {request.path} ===")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Remote addr: {request.remote_addr}")
    if request.is_json:
        logger.info(f"JSON data: {request.json}")
    logger.info(f"Query params: {request.args}")
    logger.info("=== END REQUEST INFO ===")

def log_response(response, status_code=200):
    """Log details of an outgoing response."""
    logger.info(f"=== OUTGOING RESPONSE: {status_code} ===")
    if hasattr(response, 'json'):
        try:
            logger.info(f"JSON data: {response.json()}")
        except:
            logger.info(f"Response text: {response.text[:500]}")
    logger.info("=== END RESPONSE INFO ===")

def log_step(step_name, details=None):
    """Log a step in the tour generation process."""
    logger.info(f"=== STEP: {step_name} ===")
    if details:
        logger.info(f"Details: {details}")

def log_error(error, context=None):
    """Log an error with context."""
    logger.error(f"=== ERROR: {error} ===")
    if context:
        logger.error(f"Context: {context}")
    logger.error(f"Exception type: {type(error).__name__}")
    logger.error(f"Exception args: {error.args}")
    import traceback
    logger.error(f"Traceback: {traceback.format_exc()}")

def log_api_call(service_name, url, method="GET", data=None):
    """Log an API call to another service."""
    logger.info(f"=== API CALL: {service_name} ===")
    logger.info(f"URL: {url}")
    logger.info(f"Method: {method}")
    if data:
        logger.info(f"Data: {data}")

def log_api_response(service_name, status_code, response_data=None):
    """Log an API response from another service."""
    logger.info(f"=== API RESPONSE: {service_name} ===")
    logger.info(f"Status code: {status_code}")
    if response_data:
        logger.info(f"Response data: {response_data}")

def log_job_update(job_id, status, progress=None):
    """Log a job status update."""
    logger.info(f"=== JOB UPDATE: {job_id} ===")
    logger.info(f"Status: {status}")
    if progress:
        logger.info(f"Progress: {progress}")

# Export all logging functions
__all__ = [
    'logger', 
    'log_request', 
    'log_response', 
    'log_step', 
    'log_error',
    'log_api_call',
    'log_api_response',
    'log_job_update'
]