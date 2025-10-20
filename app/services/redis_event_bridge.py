"""
Redis Event Bridge - Enables communication between Celery workers and Flask-SocketIO
"""
import json
import redis
import os
from typing import Dict, Any, Optional
from flask import current_app


class RedisEventBridge:
    """Publishes events to Redis that Flask-SocketIO will forward to WebSocket clients"""

    CHANNEL = 'websocket_events'

    def __init__(self):
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        self.redis_client = redis.from_url(redis_url)

    def publish_task_update(self, task_id: str, update_data: Dict[str, Any]):
        """Publish a task update event to Redis"""
        event = {
            'event': 'task_update',
            'task_id': task_id,
            'data': update_data
        }
        self.redis_client.publish(self.CHANNEL, json.dumps(event))

    def publish_user_notification(self, user_id: str, notification_data: Dict[str, Any]):
        """Publish a user notification event to Redis"""
        event = {
            'event': 'user_notification',
            'user_id': user_id,
            'data': notification_data
        }
        self.redis_client.publish(self.CHANNEL, json.dumps(event))


# Singleton instance
_redis_bridge: Optional[RedisEventBridge] = None


def get_redis_event_bridge() -> RedisEventBridge:
    """Get or create Redis event bridge instance"""
    global _redis_bridge
    if _redis_bridge is None:
        _redis_bridge = RedisEventBridge()
    return _redis_bridge
