from flask import Blueprint, request, jsonify
from app.bot.core import handle_update


main = Blueprint('main', __name__)

@main.route('/')
def index():
    return "🤖 Новостной бот работает!"

@main.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint для Telegram"""
    return handle_update()

@main.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "ok", "message": "Service is healthy"})

# Другие маршруты...