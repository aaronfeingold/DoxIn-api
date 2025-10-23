"""
Flask application entry point
"""
import os
import sys
from pathlib import Path
from app import create_app, socketio
from config import Config
# Add the backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

app = create_app()

if __name__ == '__main__':
    # Validate AI API keys
    Config.validate_ai_api_keys()

    # Use socketio.run instead of app.run for WebSocket support
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_ENV') == 'development'
    )
