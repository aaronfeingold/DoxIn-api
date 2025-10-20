"""
Response formatting utilities
Standardizes API response patterns across services
"""
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from flask import current_app


def success_response(data: Any = None, message: str = None, processing_time_ms: int = None, **kwargs) -> Dict[str, Any]:
    """Standard success response format"""
    response = {
        'success': True,
        'timestamp': datetime.utcnow().isoformat()
    }

    if data is not None:
        response['data'] = data
    if message:
        response['message'] = message
    if processing_time_ms is not None:
        response['processing_time_ms'] = processing_time_ms

    # Add any additional fields
    response.update(kwargs)

    return response


def error_response(error: str, details: str = None, status_code: int = None, **kwargs) -> Dict[str, Any]:
    """Standard error response format"""
    response = {
        'success': False,
        'error': error,
        'timestamp': datetime.utcnow().isoformat()
    }

    if details:
        response['details'] = details
    if status_code:
        response['status_code'] = status_code

    # Add any additional fields
    response.update(kwargs)

    return response


def processing_response(task_id: str, status: str = 'queued', message: str = None, **kwargs) -> Dict[str, Any]:
    """Standard async processing response format"""
    response = {
        'success': True,
        'task_id': task_id,
        'status': status,
        'timestamp': datetime.utcnow().isoformat()
    }

    if message:
        response['message'] = message

    # Add any additional fields
    response.update(kwargs)

    return response


def generate_task_id() -> str:
    """Generate unique task ID"""
    return str(uuid.uuid4())


def generate_unique_id() -> str:
    """Generate unique identifier"""
    return str(uuid.uuid4())


def iso_timestamp() -> str:
    """Get current UTC timestamp in ISO format"""
    return datetime.utcnow().isoformat()


def log_error(message: str, error: Exception = None, extra_data: Dict[str, Any] = None) -> None:
    """Standardized error logging"""
    log_msg = f"{message}"
    if error:
        log_msg += f": {str(error)}"
    if extra_data:
        log_msg += f" | Data: {extra_data}"

    current_app.logger.error(log_msg)


def log_info(message: str, extra_data: Dict[str, Any] = None) -> None:
    """Standardized info logging"""
    log_msg = message
    if extra_data:
        log_msg += f" | Data: {extra_data}"

    current_app.logger.info(log_msg)


def validate_uuid(uuid_string: str) -> bool:
    """Validate UUID format"""
    try:
        uuid.UUID(uuid_string)
        return True
    except (ValueError, TypeError):
        return False