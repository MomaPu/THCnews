import json
import os
from datetime import datetime, timedelta
from typing import List
from urllib import request

from flask import jsonify

from app import create_app
from app.bot.main import root_dir
from app.models.models import NewsPost, PostComment, NewsSource


def filter_news_by_time_db(db, NewsPost, hours: int):
	"""Фильтрует новости из БД за указанное количество часов"""
	try:
		time_threshold = datetime.now() - timedelta(hours=hours)
		filtered_news = NewsPost.query.filter(
			NewsPost.publish_date >= time_threshold
		).order_by(NewsPost.publish_date.desc()).all()

		return filtered_news
	except Exception as e:
		print(f"Error filtering news from DB: {e}")
		return []


def get_bad_comments_from_json(limit=20):
	"""Получает плохие комментарии из JSON файла"""
	try:
		json_path = os.path.join(root_dir, 'bad_comments.json')

		if not os.path.exists(json_path):
			print("Файл bad_comments.json не найден")
			return []

		with open(json_path, 'r', encoding='utf-8') as f:
			comments = json.load(f)

		# Сортируем по дате обнаружения (новые сначала)
		comments.sort(key=lambda x: x.get('detection_date', ''), reverse=True)

		return comments[:limit]

	except Exception as e:
		print(f"Ошибка при чтении JSON файла: {e}")
		return []


def save_bad_comment(comment_data):
	"""Сохраняет негативный комментарий в JSON файл, избегая дубликатов"""
	try:
		bad_comments_path = os.path.join(root_dir, 'bad_comments.json')

		# Загружаем существующие комментарии
		if os.path.exists(bad_comments_path):
			with open(bad_comments_path, 'r', encoding='utf-8') as f:
				try:
					comments = json.load(f)
				except json.JSONDecodeError:
					comments = []
		else:
			comments = []

		# Проверяем, существует ли уже такой комментарий
		comment_exists = any(
			comment['platform_comment_id'] == comment_data['platform_comment_id'] and
			comment['post_id'] == comment_data['post_id'] and
			comment['platform'] == comment_data['platform']
			for comment in comments
		)

		if not comment_exists:
			# Добавляем дату обнаружения
			comment_data['detection_date'] = datetime.now().isoformat()

			# Добавляем новый комментарий
			comments.append(comment_data)

			# Сохраняем обратно
			with open(bad_comments_path, 'w', encoding='utf-8') as f:
				json.dump(comments, f, ensure_ascii=False, indent=2)

			print(f"✅ Комментарий {comment_data['platform_comment_id']} добавлен в JSON")
			return True
		else:
			print(f"⚠️ Комментарий {comment_data['platform_comment_id']} уже существует, пропускаем")
			return False

	except Exception as e:
		print(f"❌ Ошибка при сохранении в JSON: {e}")
		return False
def cleanup_old_bad_comments(days: int = 30):
	"""Удаляет старые комментарии старше указанного количества дней"""
	try:
		from datetime import datetime, timedelta

		file_path = 'bad_comments.json'
		if os.path.exists(file_path):
			with open(file_path, 'r', encoding='utf-8') as f:
				comments = json.load(f)

			# Фильтруем комментарии
			cutoff_date = datetime.now() - timedelta(days=days)
			filtered_comments = [
				c for c in comments
				if datetime.fromisoformat(c.get('detection_date', '2000-01-01')) >= cutoff_date
			]

			# Сохраняем обратно
			with open(file_path, 'w', encoding='utf-8') as f:
				json.dump(filtered_comments, f, ensure_ascii=False, indent=2, default=str)

		return True
	except Exception as e:
		print(f"Error cleaning up bad comments: {e}")
		return False

def filter_news_by_time(hours: int):
	"""Фильтрует новости за указанное количество часов"""
	try:
		with open('parsing_results.json', 'r', encoding='utf-8') as f:
			news_data = json.load(f)

		time_threshold = datetime.now() - timedelta(hours=hours)
		filtered_news = []

		for news_item in news_data:
			news_time = datetime.fromisoformat(news_item.get('publish', ''))
			if news_time >= time_threshold:
				filtered_news.append(news_item)

		return filtered_news
	except Exception as e:
		print(f"Error filtering news: {e}")
		return []


def split_long_message(message: str, max_length: int = 4000) -> List[str]:
	"""Разбивает длинное сообщение на части"""
	if len(message) <= max_length:
		return [message]

	parts = []
	while message:
		if len(message) <= max_length:
			parts.append(message)
			break

		# Ищем место для разрыва по переносу строки или точке
		split_index = max_length
		for delimiter in ['\n\n', '\n', '. ', ', ', ' ']:
			index = message.rfind(delimiter, 0, max_length)
			if index != -1:
				split_index = index + len(delimiter)
				break

		parts.append(message[:split_index])
		message = message[split_index:]

	return parts


def handle_update():
	"""Обрабатывает webhook обновления от Telegram"""
	try:
		# Создаем приложение для работы с БД
		app = create_app()

		with app.app_context():
			update = request.get_json()

			if not update:
				return jsonify({"status": "error", "message": "No JSON data"}), 400

			# Здесь можно обрабатывать разные типы обновлений
			if 'message' in update:
				return _handle_message(update['message'])
			elif 'callback_query' in update:
				return _handle_callback(update['callback_query'])
			else:
				return jsonify({"status": "ok", "message": "Update type not supported"})

	except Exception as e:
		print(f"Error handling update: {e}")
		return jsonify({"status": "error", "message": str(e)}), 500


def _handle_message(message):
	"""Обрабатывает текстовые сообщения"""
	try:
		chat_id = message['chat']['id']
		text = message.get('text', '')

		print(f"📨 Received message from {chat_id}: {text}")

		# Простая обработка команд
		if text.startswith('/'):
			return _handle_command(chat_id, text)
		else:
			return jsonify({"status": "ok", "message": "Message processed"})

	except Exception as e:
		print(f"Error handling message: {e}")
		return jsonify({"status": "error", "message": str(e)}), 500


def _handle_command(chat_id, command):
	"""Обрабатывает команды бота"""
	try:
		if command == '/start' or command == '/help':
			response = {
				"method": "sendMessage",
				"chat_id": chat_id,
				"text": "🤖 Новостной бот\n\n"
						"Доступные команды:\n"
						"/news - Последние новости\n"
						"/comments - Комментарии для модерации\n"
						"/stats - Статистика",
				"parse_mode": "HTML"
			}

		elif command == '/news':
			# Получаем последние новости из БД
			news = NewsPost.query.order_by(NewsPost.publish_date.desc()).limit(5).all()

			if news:
				text = "📰 Последние новости:\n\n"
				for i, item in enumerate(news, 1):
					text += f"{i}. {item.text[:50]}...\n"
					text += f"   📅 {item.publish_date.strftime('%d.%m.%Y %H:%M')}\n"
					text += f"   🔗 {item.url}\n\n"
			else:
				text = "📭 Новостей пока нет"

			response = {
				"method": "sendMessage",
				"chat_id": chat_id,
				"text": text,
				"parse_mode": "HTML"
			}

		elif command == '/comments':
			# Получаем комментарии для модерации
			from .core import get_bad_comments_from_json
			comments = get_bad_comments_from_json(limit=5)

			if comments:
				text = "🚨 Комментарии для модерации:\n\n"
				for i, comment in enumerate(comments, 1):
					text += f"{i}. {comment.get('text', '')[:50]}...\n"
					text += f"   👤 {comment.get('user_id', 'Unknown')}\n"
					text += f"   📅 {comment.get('publish_date', '')}\n\n"
			else:
				text = "✅ Нет комментариев для модерации"

			response = {
				"method": "sendMessage",
				"chat_id": chat_id,
				"text": text,
				"parse_mode": "HTML"
			}

		elif command == '/stats':
			# Статистика из БД
			news_count = NewsPost.query.count()
			comments_count = PostComment.query.count()
			sources_count = NewsSource.query.count()

			text = f"📊 Статистика:\n\n"
			text += f"📰 Новостей: {news_count}\n"
			text += f"💬 Комментариев: {comments_count}\n"
			text += f"🌐 Источников: {sources_count}"

			response = {
				"method": "sendMessage",
				"chat_id": chat_id,
				"text": text,
				"parse_mode": "HTML"
			}

		else:
			response = {
				"method": "sendMessage",
				"chat_id": chat_id,
				"text": "❌ Неизвестная команда. Используйте /help для списка команд",
				"parse_mode": "HTML"
			}

		return jsonify(response)

	except Exception as e:
		print(f"Error handling command: {e}")
		error_response = {
			"method": "sendMessage",
			"chat_id": chat_id,
			"text": "❌ Произошла ошибка при обработке команды",
			"parse_mode": "HTML"
		}
		return jsonify(error_response)


def _handle_callback(callback_query):
	"""Обрабатывает callback queries от inline клавиатур"""
	try:
		chat_id = callback_query['message']['chat']['id']
		data = callback_query['data']

		print(f"🔘 Callback from {chat_id}: {data}")

		# Здесь можно обрабатывать разные callback действия
		response = {
			"method": "answerCallbackQuery",
			"callback_query_id": callback_query['id'],
			"text": "Действие выполнено"
		}

		return jsonify(response)

	except Exception as e:
		print(f"Error handling callback: {e}")
		return jsonify({"status": "error", "message": str(e)}), 500


# Вспомогательные функции для webhook
def set_webhook(url):
	"""Устанавливает webhook для Telegram бота"""
	import requests
	from app.bot.main import BOT_TOKEN

	try:
		response = requests.post(
			f'https://api.telegram.org/bot{BOT_TOKEN}/setWebhook',
			json={'url': url}
		)
		return response.json()
	except Exception as e:
		return {'ok': False, 'error': str(e)}


def delete_webhook():
	"""Удаляет webhook"""
	import requests
	from app.bot.main import BOT_TOKEN

	try:
		response = requests.post(
			f'https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook'
		)
		return response.json()
	except Exception as e:
		return {'ok': False, 'error': str(e)}