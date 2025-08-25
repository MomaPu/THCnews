from flask import Flask, request, jsonify
from app.bot.core import handle_update

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    handle_update(update)
    return jsonify({'status': 'ok'})