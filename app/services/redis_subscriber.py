"""
Redis Subscriber - Listens for events from Celery workers and forwards to WebSocket clients
"""
import json
import redis
import threading
import os


class RedisSubscriber:
    """Subscribes to Redis events and forwards them to WebSocket clients"""

    CHANNEL = 'websocket_events'

    def __init__(self, socketio):
        self.socketio = socketio
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        self.redis_client = redis.from_url(redis_url)
        self.pubsub = self.redis_client.pubsub()
        self.thread = None
        self.running = False

    def start(self):
        """Start listening for Redis events"""
        if self.running:
            return

        self.running = True
        self.pubsub.subscribe(self.CHANNEL)

        # Start listener thread
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()
        print(f"Redis subscriber started, listening on channel: {self.CHANNEL}")

    def stop(self):
        """Stop listening for Redis events"""
        self.running = False
        if self.pubsub:
            self.pubsub.unsubscribe(self.CHANNEL)
        if self.thread:
            self.thread.join(timeout=1)

    def _listen(self):
        """Listen for messages on Redis channel"""
        for message in self.pubsub.listen():
            if not self.running:
                break

            if message['type'] == 'message':
                try:
                    event_data = json.loads(message['data'])
                    self._handle_event(event_data)
                except Exception as e:
                    print(f"Error handling Redis event: {e}")

    def _handle_event(self, event_data):
        """Handle incoming event from Redis"""
        event_type = event_data.get('event')

        if event_type == 'task_update':
            # Forward task update to WebSocket clients in task room
            task_id = event_data.get('task_id')
            data = event_data.get('data', {})
            data['task_id'] = task_id

            room = f"task_{task_id}"
            self.socketio.emit('task_update', data, room=room)
            print(f"Forwarded task_update to room {room}: {data.get('type')}")

        elif event_type == 'user_notification':
            # Forward user notification to WebSocket clients in user's notification room
            user_id = event_data.get('user_id')
            data = event_data.get('data', {})

            room = f"user_{user_id}_notifications"
            self.socketio.emit('user_notification', data, room=room)
            print(f"Forwarded user_notification to room {room}: {data.get('type')}")


# Singleton instance
_redis_subscriber = None


def init_redis_subscriber(socketio):
    """Initialize and start Redis subscriber"""
    global _redis_subscriber
    _redis_subscriber = RedisSubscriber(socketio)
    _redis_subscriber.start()
    return _redis_subscriber


def get_redis_subscriber():
    """Get Redis subscriber instance"""
    return _redis_subscriber
