"""
Simple WebSocket Manager - Handles real-time updates
Replaces: websocket_service.py, websocket_events.py
"""
import time
from typing import Dict, Any, Optional
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import current_app, request


class WebSocketManager:
    """Simplified WebSocket manager for real-time LLM processing updates"""

    def __init__(self, socketio: SocketIO):
        self.socketio = socketio

    # === CONNECTION MANAGEMENT ===

    def handle_connect(self):
        """Handle client connection"""
        current_app.logger.info(f"Client connected: {request.sid}")
        emit('connected', {'message': 'Connected to real-time updates'})

    def handle_disconnect(self):
        """Handle client disconnection"""
        current_app.logger.info(f"Client disconnected: {request.sid}")

    def join_task_room(self, task_id: str):
        """Join a task room for real-time updates"""
        room = f"task_{task_id}"
        join_room(room)
        current_app.logger.info(f"Session {request.sid} joined room {room}")
        emit('joined_task', {'task_id': task_id, 'room': room})

    def leave_task_room(self, task_id: str):
        """Leave a task room"""
        room = f"task_{task_id}"
        leave_room(room)
        current_app.logger.info(f"Session {request.sid} left room {room}")

    def join_user_notifications(self, user_id: str):
        """Join user's personal notification room"""
        room = f"user_{user_id}_notifications"
        join_room(room)
        current_app.logger.info(f"Session {request.sid} joined notification room {room}")
        emit('joined_notifications', {'user_id': user_id, 'room': room})

    # === REAL-TIME UPDATES ===

    def send_task_update(self, task_id: str, update_data: Dict[str, Any]):
        """Send update to all clients watching this task"""
        room = f"task_{task_id}"
        update_data['timestamp'] = int(time.time() * 1000)
        update_data['task_id'] = task_id

        self.socketio.emit('task_update', update_data, room=room)

    def send_progress(self, task_id: str, progress: int, message: str, stage: str = None):
        """Send progress update"""
        self.send_task_update(task_id, {
            'type': 'progress',
            'progress': progress,
            'message': message,
            'stage': stage
        })

    def send_streaming_text(self, task_id: str, text: str, stage: str = None):
        """Send streaming text update"""
        self.send_task_update(task_id, {
            'type': 'streaming_text',
            'text': text,
            'stage': stage
        })

    def send_stage_start(self, task_id: str, stage: str, description: str):
        """Send stage start notification"""
        self.send_task_update(task_id, {
            'type': 'stage_start',
            'stage': stage,
            'description': description
        })

    def send_stage_complete(self, task_id: str, stage: str, result: Dict = None):
        """Send stage completion notification"""
        self.send_task_update(task_id, {
            'type': 'stage_complete',
            'stage': stage,
            'result': result or {}
        })

    def send_task_complete(self, task_id: str, result: Dict[str, Any], user_id: str = None):
        """Send task completion with final results"""
        self.send_task_update(task_id, {
            'type': 'complete',
            'result': result
        })

        # Also broadcast to user's personal notification room
        if user_id:
            self.send_user_notification(user_id, {
                'type': 'job_completed',
                'task_id': task_id,
                'status': 'completed',
                'filename': result.get('filename'),
                'timestamp': int(time.time() * 1000)
            })

    def send_task_error(self, task_id: str, error: str, stage: str = None, user_id: str = None, filename: str = None):
        """Send error notification"""
        self.send_task_update(task_id, {
            'type': 'error',
            'error': error,
            'stage': stage
        })

        # Also broadcast to user's personal notification room
        if user_id:
            self.send_user_notification(user_id, {
                'type': 'job_failed',
                'task_id': task_id,
                'status': 'failed',
                'error': error,
                'filename': filename,
                'timestamp': int(time.time() * 1000)
            })

    def send_user_notification(self, user_id: str, notification_data: Dict[str, Any]):
        """Send notification to a specific user's notification room"""
        room = f"user_{user_id}_notifications"
        self.socketio.emit('user_notification', notification_data, room=room)
        current_app.logger.info(f"Sent user notification to {room}: {notification_data.get('type')}")

    def send_ping_response(self):
        """Handle ping/pong for connection testing"""
        emit('pong', {'timestamp': int(time.time() * 1000)})

    # === EVENT HANDLERS ===

    def handle_join_task(self, data: Dict[str, Any]):
        """Handle client joining a task room"""
        task_id = data.get('task_id')
        if not task_id:
            emit('error', {'message': 'Missing task_id'})
            return
        self.join_task_room(task_id)

    def handle_leave_task(self, data: Dict[str, Any]):
        """Handle client leaving a task room"""
        task_id = data.get('task_id')
        if not task_id:
            emit('error', {'message': 'Missing task_id'})
            return
        self.leave_task_room(task_id)

    def handle_ping(self):
        """Handle ping for connection testing"""
        self.send_ping_response()

    def handle_join_user_notifications(self, data: Dict[str, Any]):
        """Handle client joining their notification room"""
        user_id = data.get('user_id')
        if not user_id:
            emit('error', {'message': 'Missing user_id'})
            return
        self.join_user_notifications(user_id)


# === SINGLETON PATTERN ===

_websocket_manager: Optional[WebSocketManager] = None


def init_websocket_manager(socketio: SocketIO) -> WebSocketManager:
    """Initialize WebSocket manager"""
    global _websocket_manager
    _websocket_manager = WebSocketManager(socketio)

    # Register event handlers
    @socketio.on('connect')
    def handle_connect():
        _websocket_manager.handle_connect()

    @socketio.on('disconnect')
    def handle_disconnect():
        _websocket_manager.handle_disconnect()

    @socketio.on('join_task')
    def handle_join_task(data):
        _websocket_manager.handle_join_task(data)

    @socketio.on('leave_task')
    def handle_leave_task(data):
        _websocket_manager.handle_leave_task(data)

    @socketio.on('ping')
    def handle_ping():
        _websocket_manager.handle_ping()

    @socketio.on('join_user_notifications')
    def handle_join_user_notifications(data):
        _websocket_manager.handle_join_user_notifications(data)

    return _websocket_manager


def get_websocket_manager() -> Optional[WebSocketManager]:
    """Get WebSocket manager instance"""
    return _websocket_manager
