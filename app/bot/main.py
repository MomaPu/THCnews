import sys
import telebot
from telebot import types
import os
from dotenv import load_dotenv
import threading
import time
from datetime import datetime, timedelta
import schedule

# Добавляем корневую директорию в Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.append(root_dir)

# Загружаем переменные окружения
env_path = os.path.join(root_dir, '.env')
if os.path.exists(env_path):
	load_dotenv(env_path)
	print(".env файл найден и загружен")
else:
	print("Ошибка: .env файл не найден!")
	exit(1)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

# Инициализируем бота
bot = telebot.TeleBot(BOT_TOKEN)

# Создаем Flask приложение с правильной конфигурацией
try:
	from app import create_app, db
	from app.models.models import NewsPost, PostComment

	# Создаем приложение
	app = create_app()

	print("Flask приложение и БД инициализированы")

except ImportError as e:
	print(f"Ошибка импорта модулей: {e}")
	exit(1)

# Переменная для отслеживания последнего запуска парсера
last_parser_run = None
parser_running = False


# Клавиатуры
def get_main_keyboard():
	keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
	keyboard.add(types.KeyboardButton("Последние новости"))
	keyboard.add(types.KeyboardButton("Выбрать период"))
	keyboard.add(types.KeyboardButton("Комментарии для модерации"))
	keyboard.add(types.KeyboardButton("Комментарии-упоминания"))
	keyboard.add(types.KeyboardButton("Запустить парсер"))
	keyboard.add(types.KeyboardButton("Статус парсера"))
	return keyboard


def get_time_selection_keyboard():
	keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
	keyboard.add(types.KeyboardButton("12 часов"))
	keyboard.add(types.KeyboardButton("24 часа"))
	keyboard.add(types.KeyboardButton("36 часов"))
	keyboard.add(types.KeyboardButton("48 часов"))
	keyboard.add(types.KeyboardButton("60 часов"))
	keyboard.add(types.KeyboardButton("Комментарии для модерации"))
	keyboard.add(types.KeyboardButton("Главное меню"))
	return keyboard


# Функции для работы с БД в контексте приложения
def get_news_by_period(hours):
	"""Получает новости за период в контексте приложения"""
	with app.app_context():
		from app.bot.core import filter_news_by_time_db
		return filter_news_by_time_db(db, NewsPost, hours)


def get_bad_comments_db_wrapper(limit=20):
	"""Получает плохие комментарии в контексте приложения"""
	with app.app_context():
		from app.bot.core import get_bad_comments_from_json
		return get_bad_comments_from_json(limit)


def get_mention_comments_db(limit=20):
	"""Получает комментарии с sentiment 'Упоминание ТНС' из БД"""
	with app.app_context():
		result = db.session.execute(db.text("SELECT current_database()")).scalar()
		print(f"📊 Telegram Service подключен к БД: {result}")
		try:
			print("🔍 Ищем комментарии с sentiment 'Упоминание ТНС' в БД...")
			db.session.expire_all()
			# Проверим сначала все существующие sentiment'ы
			all_sentiments = db.session.query(PostComment.sentiment).distinct().all()
			print(f"📊 Все sentiment'ы в БД: {[s[0] for s in all_sentiments]}")

			comments = PostComment.query.filter(
				PostComment.sentiment == 'Упоминание ТНС'
			).order_by(PostComment.publish_date.desc()).limit(limit).all()

			print(f"✅ Найдено комментариев с 'Упоминание ТНС': {len(comments)}")

			# Преобразуем в словари для единообразия
			result = []
			for comment in comments:
				result.append({
					'text': comment.text,
					'user_id': comment.platform_user_id,
					'publish_date': comment.publish_date.isoformat() if comment.publish_date else 'Неизвестно',
					'likes_count': comment.likes_count,
					'sentiment': comment.sentiment,
					'post_title': comment.post.text[
								  :100] + '...' if comment.post and comment.post.text else 'Без названия',
					'post_url': comment.post.url if comment.post else 'Отсутствует'
				})

			return result

		except Exception as e:
			print(f"❌ Ошибка при получении комментариев-упоминаний: {e}")
			import traceback
			traceback.print_exc()
			return []

def show_mention_comments(message):
    try:
        # Получаем комментарии-упоминания из БД
        mention_comments = get_mention_comments_db(limit=100)

        if mention_comments:
            response = "🔍 Комментарии-упоминания:\n\n"

            for i, comment in enumerate(mention_comments, 1):
                comment_text = f"{i}. {comment.get('text', 'Без текста')}\n"
                comment_text += f"👤 {comment.get('user_id', 'Неизвестно')}\n"
                comment_text += f"📅 {comment.get('publish_date', 'Неизвестно')}\n"
                comment_text += f"👍 {comment.get('likes_count', 0)}\n"
                comment_text += f"📝 {comment.get('post_title', 'Без названия')}\n\n"
                comment_text += f"{comment.get('post_url', 'Отсутствует')}\n\n"

                if len(response) + len(comment_text) > 4000:
                    bot.send_message(message.chat.id, response)
                    response = "Продолжение упоминаний:\n\n"

                response += comment_text

            if response.strip():
                bot.send_message(message.chat.id, response)

        else:
            bot.send_message(message.chat.id, "✅ Комментариев-упоминаний не найдено.")

    except Exception as e:
        bot.send_message(message.chat.id, "❌ Произошла ошибка при загрузке комментариев-упоминаний.")
        print(f"Error: {e}")

def get_latest_news(limit=10):
	"""Получает последние новости в контексте приложения"""
	with app.app_context():
		return NewsPost.query.order_by(NewsPost.publish_date.desc()).limit(limit).all()


def run_master_parser():
	"""Запускает мастер-парсер в отдельном потоке"""
	global parser_running, last_parser_run

	if parser_running:
		return "❌ Парсер уже запущен!"

	parser_running = True

	def parser_thread():
		global parser_running, last_parser_run

		try:
			print("🚀 Запуск мастер-парсера...")

			# Импортируем здесь чтобы избежать циклических импортов
			from app.bot.master_parser import run_parsers

			results = run_parsers()
			last_parser_run = datetime.now()

			# Отправляем уведомление админу
			if ADMIN_ID:
				try:
					total = results.get('total', 0)
					message = f"✅ Парсер завершил работу\n\n"
					message += f"📱 Telegram: {results.get('telegram', {}).get('saved', 0)} постов\n"
					message += f"🔵 VK: {results.get('vk', {}).get('saved', 0)} постов\n"
					message += f"🟠 OK: {results.get('odnoklassniki', {}).get('saved', 0)} постов\n"
					message += f"🌐 Веб-сайты: {results.get('web', {}).get('saved', 0)} постов\n"
					message += f"📈 Всего: {total} постов\n"
					message += f"⏰ Время: {last_parser_run.strftime('%Y-%m-%d %H:%M:%S')}"

					bot.send_message(ADMIN_ID, message)
				except Exception as e:
					print(f"Ошибка отправки уведомления: {e}")

			print(f"✅ Парсер завершил работу. Найдено {total} постов")

		except Exception as e:
			print(f"❌ Ошибка в парсере: {e}")
			if ADMIN_ID:
				try:
					bot.send_message(ADMIN_ID, f"❌ Ошибка парсера: {str(e)[:1000]}")
				except:
					pass
		finally:
			parser_running = False

	# Запускаем в отдельном потоке
	thread = threading.Thread(target=parser_thread)
	thread.daemon = True
	thread.start()

	return "✅ Парсер запущен! Результаты будут позже."


def schedule_daily_parser():
	"""Настраивает ежедневный запуск парсера"""

	def daily_parser_job():
		if not parser_running:
			run_master_parser()
			print("📅 Ежедневный парсер запущен по расписанию")

	# Запуск каждый день в 9:00
	schedule.every().day.at("09:00").do(daily_parser_job)


	print("📅 Планировщик ежедневного парсера настроен")


def schedule_checker():
	"""Запускает проверку расписания в отдельном потоке"""
	while True:
		schedule.run_pending()
		time.sleep(60)


# Обработчики команд
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
	bot.reply_to(
		message,
		"Добро пожаловать в новостной бот!\n"
		"Вы можете:\n"
		"- Получить последние новости\n"
		"- Выбрать период для показа новостей\n"
		"- Просмотреть комментарии для модерации\n"
		"- Просмотреть комментарии-упоминания\n"
		"- Запустить парсер вручную\n"
		"- Проверить статус парсера",
		reply_markup=get_main_keyboard()
	)

@bot.message_handler(func=lambda message: message.text == "Комментарии-упоминания")
def handle_mention_comments(message):
    print("Обработка кнопки 'Комментарии-упоминания'")
    show_mention_comments(message)

@bot.message_handler(commands=['run_parser'])
def run_parser_command(message):
	"""Запуск парсера через команду"""
	if str(message.chat.id) != ADMIN_ID:
		bot.reply_to(message, "❌ Эта команда только для администратора!")
		return

	result = run_master_parser()
	bot.reply_to(message, result)


@bot.message_handler(commands=['parser_status'])
def parser_status_command(message):
	"""Статус парсера"""
	status = get_parser_status()
	bot.reply_to(message, status)


@bot.message_handler(func=lambda message: message.text == "Последние новости")
def handle_latest_news(message):
	print("Обработка кнопки 'Последние новости'")
	show_latest_news(message)


@bot.message_handler(func=lambda message: message.text == "Комментарии для модерации")
def handle_bad_comments(message):
	print("Обработка кнопки 'Комментарии для модерации'")
	show_bad_comments(message)


@bot.message_handler(func=lambda message: message.text == "Запустить парсер")
def handle_run_parser(message):
	"""Обработка кнопки запуска парсера"""
	if str(message.chat.id) != ADMIN_ID:
		bot.reply_to(message, "❌ Эта функция только для администратора!")
		return

	result = run_master_parser()
	bot.reply_to(message, result)


@bot.message_handler(func=lambda message: message.text == "Статус парсера")
def handle_parser_status(message):
	"""Обработка кнопки статуса парсера"""
	status = get_parser_status()
	bot.reply_to(message, status)


@bot.message_handler(func=lambda message: message.text == "Выбрать период")
def select_period(message):
	bot.send_message(
		message.chat.id,
		"Выберите период для показа новостей:",
		reply_markup=get_time_selection_keyboard()
	)


@bot.message_handler(func=lambda message: message.text in ["12 часов", "24 часа", "36 часов", "48 часов", "60 часов"])
def handle_period_selection(message):
	hours_map = {
		"12 часов": 12,
		"24 часа": 24,
		"36 часов": 36,
		"48 часов": 48,
		"60 часов": 60
	}

	hours = hours_map[message.text]
	show_news_for_period(message, hours)


@bot.message_handler(func=lambda message: message.text == "Главное меню")
def main_menu(message):
	bot.send_message(
		message.chat.id,
		"Главное меню:",
		reply_markup=get_main_keyboard()
	)


def get_parser_status():
	"""Возвращает статус парсера"""
	status = "📊 Статус парсера:\n\n"

	if parser_running:
		status += "🟡 Парсер запущен и работает...\n"
	else:
		status += "🟢 Парсер не активен\n"

	if last_parser_run:
		status += f"⏰ Последний запуск: {last_parser_run.strftime('%Y-%m-%d %H:%M:%S')}\n"

		# Время с последнего запуска
		time_diff = datetime.now() - last_parser_run
		hours_diff = time_diff.total_seconds() / 3600
		status += f"⏳ Прошло времени: {hours_diff:.1f} часов\n"
	else:
		status += "⏰ Парсер еще не запускался\n"

	# Статистика из БД
	with app.app_context():
		news_count = NewsPost.query.count()
		comments_count = PostComment.query.count()

	status += f"\n📊 Статистика БД:\n"
	status += f"📰 Новостей: {news_count}\n"
	status += f"💬 Комментариев: {comments_count}\n"

	return status


def show_news_for_period(message, hours):
	try:
		# Получаем новости из БД за указанный период
		filtered_news = get_news_by_period(hours)

		if filtered_news:
			response = f"📰 Новости за последние {hours} часов:\n\n"
			for i, news in enumerate(filtered_news, 1):
				news_text = news.text if news.text else "Без текста"
				news_preview = news_text[:100] + "..." if len(news_text) > 100 else news_text

				news_item = f"{i}. {news_preview}\n"
				news_item += f"📅 {news.publish_date}\n"
				news_item += f"🔗 {news.url}\n\n"

				if len(response) + len(news_item) > 4000:
					bot.send_message(message.chat.id, response)
					response = "Продолжение:\n\n"

				response += news_item

			if response.strip():
				bot.send_message(message.chat.id, response)
		else:
			bot.send_message(message.chat.id, f"За последние {hours} часов новостей не найдено.")

	except Exception as e:
		bot.send_message(message.chat.id, "Произошла ошибка при загрузке новостей из БД.")
		print(f"Error: {e}")


def show_bad_comments(message):
	try:
		# Получаем плохие комментарии из JSON
		bad_comments = get_bad_comments_db_wrapper(limit=100)

		if bad_comments:
			response = "🚨 Комментарии для модерации:\n\n"

			for i, comment in enumerate(bad_comments, 1):
				comment_text = f"{i}. {comment.get('text', 'Без текста')}\n"
				comment_text += f"👤 {comment.get('user_id', 'Неизвестно')}\n"
				comment_text += f"📅 {comment.get('publish_date', 'Неизвестно')}\n"
				comment_text += f"👍 {comment.get('likes_count', 0)}\n"
				comment_text += f"📝 {comment.get('post_title', 'Без названия')}\n\n"
				comment_text += f"{comment.get('post_url', 'Отсутствует')}\n\n"

				if len(response) + len(comment_text) > 4000:
					bot.send_message(message.chat.id, response)
					response = "Продолжение комментариев:\n\n"

				response += comment_text

			if response.strip():
				bot.send_message(message.chat.id, response)

		else:
			bot.send_message(message.chat.id, "✅ Комментариев для модерации не найдено.")

	except Exception as e:
		bot.send_message(message.chat.id, "❌ Произошла ошибка при загрузке комментариев из JSON.")
		print(f"Error: {e}")


def show_latest_news(message):
	try:
		# Получаем последние новости из БД
		latest_news = get_latest_news(limit=100)

		if latest_news:
			response = "📰 Последние новости:\n\n"

			for i, news in enumerate(latest_news, 1):
				news_text = news.text if news.text else "Без текста"
				news_preview = news_text[:100] + "..." if len(news_text) > 100 else news_text

				news_item = f"{i}. {news_preview}\n"
				news_item += f"📅 {news.publish_date}\n"
				news_item += f"🔗 {news.url}\n\n"

				if len(response) + len(news_item) > 4000:
					bot.send_message(message.chat.id, response)
					response = "Продолжение новостей:\n\n"

				response += news_item

			if response.strip():
				bot.send_message(message.chat.id, response)
		else:
			bot.send_message(message.chat.id, "Новостей не найдено.")

	except Exception as e:
		bot.send_message(message.chat.id, "❌ Произошла ошибка при загрузке новостей.")
		print(f"Error: {e}")


# Запуск бота
if __name__ == '__main__':
	print("Бот запущен...")

	# Настраиваем ежедневный парсер
	schedule_daily_parser()

	# Запускаем планировщик в отдельном потоке
	scheduler_thread = threading.Thread(target=schedule_checker)
	scheduler_thread.daemon = True
	scheduler_thread.start()

	print("📅 Планировщик запущен")

	# Запускаем бота
	bot.infinity_polling()