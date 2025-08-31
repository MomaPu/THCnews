import asyncio
import os
import sys
import json
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.errors import MsgIdInvalidError
from telethon.tl.types import PeerUser, PeerChannel, PeerChat
from dotenv import load_dotenv

from app.bot.core import save_bad_comment

# Добавляем корневую директорию в путь
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.append(root_dir)

# Импорты после добавления пути
from app import create_app
from app.database import db
from app.models.models import NewsSource, NewsPost, PostComment
from app.services.texteditor import classify_text

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


	def _serialize_peer(self, peer):
		"""Преобразует Peer объекты в сериализуемый формат"""
		if isinstance(peer, PeerUser):
			return {'type': 'user', 'user_id': peer.user_id}
		elif isinstance(peer, PeerChannel):
			return {'type': 'channel', 'channel_id': peer.channel_id}
		elif isinstance(peer, PeerChat):
			return {'type': 'chat', 'chat_id': peer.chat_id}
		elif hasattr(peer, 'user_id'):
			return {'type': 'user', 'user_id': peer.user_id}
		elif hasattr(peer, 'channel_id'):
			return {'type': 'channel', 'channel_id': peer.channel_id}
		elif hasattr(peer, 'chat_id'):
			return {'type': 'chat', 'chat_id': peer.chat_id}
		return str(peer)

	def _serialize_message_replies(self, replies):
		"""Преобразует MessageReplies в сериализуемый словарь"""
		if not replies:
			return {}
		return {
			'replies': replies.replies,
			'replies_pts': replies.replies_pts,
			'comments': replies.comments,
			'recent_repliers': [self._serialize_peer(user_id) for user_id in
								replies.recent_repliers] if replies.recent_repliers else [],
			'channel_id': self._serialize_peer(replies.channel_id) if replies.channel_id else None,
			'max_id': replies.max_id,
			'read_max_id': replies.read_max_id
		}

	def _serialize_platform_data(self, message):
		"""Создает сериализуемый словарь platform_data"""
		platform_data = {
			'views': getattr(message, 'views', 0),
			'forwards': getattr(message, 'forwards', 0),
		}

		# Обрабатываем replies
		if hasattr(message, 'replies') and message.replies:
			platform_data['replies'] = self._serialize_message_replies(message.replies)
		else:
			platform_data['replies'] = {}

		return platform_data

	def _serialize_comment_platform_data(self, comment):
		"""Создает сериализуемый словарь platform_data для комментария"""
		platform_data = {
			'from_id': self._serialize_peer(getattr(comment, 'from_id', None)),
			'reply_to_msg_id': getattr(comment, 'reply_to_msg_id', None),
			'views': getattr(comment, 'views', 0)
		}
		return platform_data

	def _extract_user_id(self, peer):
		"""Извлекает user_id из Peer объекта"""
		if isinstance(peer, PeerUser):
			return str(peer.user_id)
		elif hasattr(peer, 'user_id'):
			return str(peer.user_id)
		elif isinstance(peer, (PeerChannel, PeerChat)):
			return None
		return str(peer)

	async def get_news(self, channels, keywords, days=3):
		"""Получает новости с подробным логированием"""
		await self.client.start()
		end_date = datetime.now(timezone.utc)
		start_date = end_date - timedelta(days=days)

		print(f"🔍 Начинаем поиск по {len(channels)} каналам")
		print(f"📋 Ключевые слова: {keywords}")
		print(f"⏰ Период: последние {days} дней")

		results = []

		with create_app().app_context():
			for channel in channels:
				try:
					print(f"\n📡 Проверяем канал: {channel}")
					source = await self._get_or_create_source(channel)
					post_count = 0

					async for message in self.client.iter_messages(channel, limit=100):
						message_date = message.date.replace(
							tzinfo=timezone.utc) if message.date.tzinfo is None else message.date

						if message_date < start_date:
							if post_count > 0:
								print(f"⏩ Пропускаем старые сообщения в {channel}")
							break

						if message.text:
							message_text = message.text.lower()
							found_keywords = []

							# Поиск ключевых слов
							for kw in keywords:
								if kw.lower() in message_text:
									found_keywords.append(kw)

							# Поиск хештегов
							found_hashtags = []
							if hasattr(message, 'entities'):
								for entity in message.entities:
									if hasattr(entity, 'type') and entity.type == 'hashtag':
										hashtag_start = entity.offset
										hashtag_end = hashtag_start + entity.length
										hashtag = message.text[hashtag_start:hashtag_end].lower()
										for kw in keywords:
											if kw.startswith('#') and kw.lower() in hashtag:
												found_hashtags.append(kw)

							if found_keywords or found_hashtags:
								post_count += 1
								print(
									f"✅ Пост {post_count}: найдены ключи - {found_keywords}, хештеги - {found_hashtags}")

								post = await self._save_post(source, message, keywords)
								comments = await self._get_comments(channel, message.id, post)

								results.append({
									'date': message_date.strftime('%Y-%m-%d %H:%M'),
									'text': message.text,
									'url': f"https://t.me/{channel}/{message.id}",
									'comments': comments,
									'id': post.id
								})

					print(f"📊 В канале {channel} найдено {post_count} подходящих постов")

				except Exception as e:
					print(f"❌ Ошибка в канале {channel}: {e}")
					continue

		print(f"\n🎯 Итого найдено постов: {len(results)}")
		return sorted(results, key=lambda x: x['date'], reverse=True)

	async def search_by_hashtag(self, channel, hashtag, days=3):
		"""Ищет посты по конкретному хештегу"""
		await self.client.start()
		end_date = datetime.now(timezone.utc)
		start_date = end_date - timedelta(days=days)

		results = []

		try:
			async for message in self.client.iter_messages(channel, limit=100):
				message_date = message.date.replace(
					tzinfo=timezone.utc) if message.date.tzinfo is None else message.date

				if message_date < start_date:
					break

				if message.text and hasattr(message, 'entities'):
					for entity in message.entities:
						if hasattr(entity, 'type') and entity.type == 'hashtag':
							hashtag_start = entity.offset
							hashtag_end = hashtag_start + entity.length
							message_hashtag = message.text[hashtag_start:hashtag_end].lower()

							if hashtag.lower() in message_hashtag:
								results.append({
									'date': message_date.strftime('%Y-%m-%d %H:%M'),
									'text': message.text,
									'url': f"https://t.me/{channel}/{message.id}"
								})
								break

		except Exception as e:
			print(f"Ошибка поиска по хештегу {hashtag}: {e}")

		return results


	async def _get_or_create_source(self, channel_name):
		"""Получает или создает источник новостей"""
		source = NewsSource.query.filter_by(
			platform='telegram',
			source_id=channel_name
		).first()

		if not source:
			source = NewsSource(
				platform='telegram',
				source_id=channel_name,
				source_name=channel_name,
				source_type='channel'
			)
			db.session.add(source)
			db.session.flush()

		return source


	async def _save_post(self, source, message, keywords):
		"""Сохраняет пост в БД"""
		post_id_str = str(message.id)

		post = NewsPost.query.filter_by(
			platform='telegram',
			platform_post_id=post_id_str
		).first()

		if not post:
			# Создаем сериализуемые данные
			platform_data = self._serialize_platform_data(message)

			post = NewsPost(
				platform='telegram',
				platform_post_id=post_id_str,
				source_id=source.id,
				text=message.text,
				url=f"https://t.me/{source.source_id}/{message.id}",
				author=source.source_name,
				publish_date=message.date,
				keywords=keywords,
				platform_data=platform_data
			)
			db.session.add(post)
			db.session.flush()

		return post

	async def _get_comments(self, channel, post_id, post):
		"""Получает комментарии к посту, сохраняет в БД и негативные в JSON"""
		comments_data = []
		negative_count = 0

		try:
			async for comment in self.client.iter_messages(channel, reply_to=post_id, limit=50):
				if comment and comment.text:
					sentiment = classify_text(comment.text)
					print(f"📝 Комментарий: {comment.text[:50]}... -> {sentiment}")

					# Сохраняем комментарий в БД
					saved_comment = await self._save_comment(post, comment, sentiment)

					# Сохраняем негативные комментарии в JSON
					if sentiment == "Негативный комментарий":
						negative_count += 1
						user_id = self._extract_user_id(getattr(comment, 'from_id', ''))

						bad_comment_data = {
							'platform_comment_id': str(comment.id),
							'post_id': post.id,
							'post_title': post.text[:100] + '...' if post.text else 'Без названия',
							'post_url': post.url,
							'text': comment.text,
							'user_id': user_id if user_id else 'unknown',
							'publish_date': comment.date.isoformat(),
							'platform': 'Telegram',
							'sentiment': sentiment,
							'platform_data': {
								'from_id': user_id if user_id else 'unknown',
								'reply_to_msg_id': getattr(comment, 'reply_to_msg_id', None)
							}
						}

						print(f"🔴 Найден негативный комментарий #{negative_count}")

						# Сохраняем только если комментария еще нет в JSON
						save_bad_comment(bad_comment_data)

					comments_data.append({
						'date': comment.date.strftime('%H:%M'),
						'text': f"[{sentiment}] {comment.text}",
						'sentiment': sentiment,
						'original_text': comment.text
					})

			print(f"📊 Итого негативных комментариев: {negative_count}")

		except MsgIdInvalidError:
			print(f"Сообщение {post_id} не имеет комментариев или ID неверный")
		except Exception as e:
			print(f"Ошибка при получении комментариев для сообщения {post_id}: {e}")

		return comments_data
	async def _save_comment(self, post, comment, sentiment):
		"""Сохраняет комментарий в БД"""
		comment_id_str = str(comment.id)
		user_id = self._extract_user_id(getattr(comment, 'from_id', ''))
		user_id_str = user_id if user_id else 'unknown'

		existing_comment = PostComment.query.filter_by(
			post_id=post.id,
			platform_comment_id=comment_id_str
		).first()

		if not existing_comment:
			# Создаем сериализуемые platform_data
			platform_data = self._serialize_comment_platform_data(comment)

			new_comment = PostComment(
				post_id=post.id,
				platform_comment_id=comment_id_str,
				platform_user_id=user_id_str,
				text=comment.text,
				sentiment=sentiment,
				publish_date=comment.date,
				likes_count=getattr(comment, 'views', 0) if hasattr(comment, 'views') else 0,
				platform_data=platform_data
			)
			db.session.add(new_comment)
			return new_comment

		return existing_comment

	async def close(self):
		await self.client.disconnect()


async def main():
	# Создаем приложение один раз
	app = create_app()

	# Передаем приложение в сервис
	service = TelegramService()

	try:
		# Используем контекст приложения
		with app.app_context():
			keywords = [
				'ТНС',
				'энерго',
				'энергосбыт',
				'электричество',
				'электроснабжение',
			]

			# Добавьте хештеги отдельно
			hashtags = [
				'#ТНС',
				'#энерго',
				'#энергосбыт',
				'#ТНСэнерго',
				'#ТНСэнергоНН'
			]

			# Объединяем ключевые слова и хештеги
			search_terms = keywords + hashtags

			news = await service.get_news(
				channels=['Dzerzhinsk_blackhole', 'tns_energo_nn'],
				keywords=search_terms,
				days=5
			)

			print(f"Найдено {len(news)} постов")
			for i, item in enumerate(news[:5], 1):
				print(f"\n{i}. {item['date']}")
				print(f"Текст: {item['text'][:100]}...")
				print(f"Ссылка: {item['url']}")
				if item['comments']:
					print(f"Комментарии ({len(item['comments'])}):")
					for j, comment in enumerate(item['comments'][:3], 1):
						print(f"  {j}. {comment['date']}: {comment['text'][:80]}...")
				else:
					print("Комментарии: нет")

	except Exception as e:
		print(f"Ошибка в main: {e}")
		import traceback
		traceback.print_exc()
	finally:
		await service.close()


if __name__ == '__main__':
	asyncio.run(main())