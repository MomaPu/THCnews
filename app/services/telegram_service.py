import asyncio
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.errors import MsgIdInvalidError
from dotenv import load_dotenv

from app.services.texteditor import classify_text  # Импортируем из texteditor

load_dotenv()

API_ID = 20304623
API_HASH = "c1622024c0ad17c26fbd6b34f1d9ef1c"


class TelegramService:
	def __init__(self):
		self.client = TelegramClient(
			'read_client',
			API_ID,
			API_HASH,
			device_model='Iphone 5',
			system_version='IOS 13',
		)

	async def get_news(self, channels, keywords, days=3):
		"""Получает новости из Telegram каналов"""
		await self.client.start()
		end_date = datetime.now(timezone.utc)
		start_date = end_date - timedelta(days=days)

		results = []
		for channel in channels:
			try:
				async for message in self.client.iter_messages(channel):
					message_date = message.date.replace(
						tzinfo=timezone.utc) if message.date.tzinfo is None else message.date

					if message_date < start_date:
						break

					if message.text and any(kw.lower() in message.text.lower() for kw in keywords):
						comments = await self._get_comments(channel, message.id)
						results.append({
							'date': message_date.strftime('%Y-%m-%d %H:%M'),
							'text': message.text,
							'url': f"https://t.me/{channel}/{message.id}",
							'comments': comments
						})
			except Exception as e:
				print(f"Ошибка при обработке канала {channel}: {e}")
				continue

		return sorted(results, key=lambda x: x['date'], reverse=True)

	async def _get_comments(self, channel, post_id):
		"""Получает комментарии к посту и классифицирует их"""
		comments = []
		try:
			async for comment in self.client.iter_messages(channel, reply_to=post_id):
				if comment and comment.text:  # Проверяем, что комментарий существует и есть текст
					# Классифицируем комментарий
					sentiment = classify_text(comment.text)

					# Добавляем метку к тексту комментария
					classified_text = f"[{sentiment}] {comment.text}"

					comments.append({
						'date': comment.date.strftime('%H:%M'),
						'text': classified_text,
						'sentiment': sentiment,
						'original_text': comment.text
					})
		except MsgIdInvalidError:
			print(f"Сообщение {post_id} не имеет комментариев или ID неверный")
		except Exception as e:
			print(f"Ошибка при получении комментариев для сообщения {post_id}: {e}")

		return comments


async def main():
	service = TelegramService()
	news = await service.get_news(
		channels=['vodokanalkzn'],
		keywords=['водоканал'],
		days=7
	)

	# Вывод результатов
	for i, item in enumerate(news[:10], 1):
		print(f"\n{i}. {item['date']}")
		print(f"Текст: {item['text'][:200]}{'...' if len(item['text']) > 200 else ''}")
		print(f"Ссылка: {item['url']}")
		if item['comments']:
			print(f"Комментарии ({len(item['comments'])}):")
			for j, comment in enumerate(item['comments'][:3], 1):
				print(f"  {j}. {comment['date']}: {comment['text'][:100]}{'...' if len(comment['text']) > 100 else ''}")
		else:
			print("Комментарии: нет")


if __name__ == '__main__':
	asyncio.run(main())