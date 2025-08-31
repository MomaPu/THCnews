import os
import sys
import vk_api
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv
import asyncio
import aiohttp
import json
from sqlalchemy.orm.exc import DetachedInstanceError

# Добавляем корневую директорию в путь
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.append(root_dir)

from app import create_app
from app.database import db
from app.models.models import NewsSource, NewsPost, PostComment
from app.services.texteditor import classify_text

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv()

VK_TOKEN = os.getenv('VK_TOKEN')
VK_VERSION = '5.131'



class VKService:
	def __init__(self):
		self.session = vk_api.VkApi(token=VK_TOKEN)
		self.vk = self.session.get_api()
		self.app = create_app()

	def _get_or_create_source(self, domain):
		"""Получает или создает источник новостей"""
		with self.app.app_context():
			source = NewsSource.query.filter_by(
				platform='vk',
				source_id=domain
			).first()

			if not source:
				# Получаем информацию о группе
				try:
					group_info = self.vk.groups.getById(group_id=domain)[0]
					source_name = group_info.get('name', domain)
				except:
					source_name = domain

				source = NewsSource(
					platform='vk',
					source_id=domain,
					source_name=source_name,
					source_type='group'
				)
				db.session.add(source)
				db.session.commit()
				db.session.refresh(source)

			return source

	def _save_post(self, source, post_data, keywords):
		"""Сохраняет пост в БД"""
		with self.app.app_context():
			try:
				post_id_str = f"{post_data.get('owner_id')}_{post_data.get('id')}"

				existing_post = NewsPost.query.filter_by(
					platform='vk',
					platform_post_id=post_id_str
				).first()

				if not existing_post:
					platform_data = {
						'likes': post_data.get('likes', {}).get('count', 0),
						'reposts': post_data.get('reposts', {}).get('count', 0),
						'views': post_data.get('views', {}).get('count', 0),
						'comments_count': post_data.get('comments', {}).get('count', 0)
					}

					# Получаем дату публикации
					publish_date = datetime.fromtimestamp(post_data.get('date', 0))

					post = NewsPost(
						platform='vk',
						platform_post_id=post_id_str,
						source_id=source.id,
						text=post_data.get('text', ''),
						url=f"https://vk.com/wall{post_id_str}",
						author=source.source_name,
						publish_date=publish_date,
						keywords=keywords,
						platform_data=platform_data
					)
					db.session.add(post)
					db.session.commit()
					db.session.refresh(post)
					return post
				else:
					return existing_post

			except Exception as e:
				db.session.rollback()
				print(f"❌ Ошибка сохранения поста: {e}")
				return None

	def _save_comment(self, post, comment_data, sentiment):
		"""Сохраняет комментарий в БД"""
		with self.app.app_context():
			try:
				comment_id_str = str(comment_data.get('id'))
				user_id = str(comment_data.get('from_id', 'unknown'))

				existing_comment = PostComment.query.filter_by(
					post_id=post.id,
					platform_comment_id=comment_id_str
				).first()

				if not existing_comment:
					platform_data = {
						'from_id': user_id,
						'likes': comment_data.get('likes', {}).get('count', 0)
					}

					# Получаем дату публикации комментария
					publish_date = datetime.fromtimestamp(comment_data.get('date', 0))

					comment = PostComment(
						post_id=post.id,
						platform_comment_id=comment_id_str,
						platform_user_id=user_id,
						text=comment_data.get('text', ''),
						sentiment=sentiment,
						publish_date=publish_date,
						likes_count=comment_data.get('likes', {}).get('count', 0),
						platform_data=platform_data
					)
					db.session.add(comment)
					return comment
				else:
					return existing_comment

			except Exception as e:
				print(f"❌ Ошибка сохранения комментария: {e}")
				return None

	def get_posts(self, domain, keywords, days=7, count=100):
		"""Получает посты из VK группы с улучшенной фильтрацией"""
		try:
			end_date = datetime.now()
			start_date = end_date - timedelta(days=days)
			start_timestamp = int(start_date.timestamp())

			all_posts = []
			offset = 0

			print(f"🔍 Ищем посты в {domain} за {days} дней...")

			while offset < count:
				response = self.vk.wall.get(
					domain=domain,
					count=100,
					offset=offset,
					filter='owner'
				)

				posts = response['items']
				if not posts:
					break

				for post in posts:
					if post.get('date', 0) < start_timestamp:
						print(f"⏰ Достигнута начальная дата")
						return all_posts

					post_text = post.get('text', '').lower()

					# Расширенная проверка ключевых слов
					keyword_found = False
					for keyword in keywords:
						# Ищем разные варианты написания
						keyword_variants = [
							keyword.lower(),
							keyword.replace(' ', '').lower(),
							keyword.replace(' ', '_').lower(),
							keyword.replace(' ', '-').lower(),
							f"#{keyword.replace(' ', '').lower()}",
							f"#{keyword.replace(' ', '_').lower()}"
						]

						for variant in keyword_variants:
							if variant in post_text:
								keyword_found = True
								break
						if keyword_found:
							break

					if keyword_found:
						all_posts.append(post)
						print(f"✅ Найден пост с ключевым словом: {post_text[:50]}...")

				offset += 100
				print(f"📊 Обработано {offset} постов, найдено {len(all_posts)}")

				if len(posts) < 100:  # Больше нет постов
					break

				time.sleep(0.2)

			return all_posts

		except Exception as e:
			print(f"❌ Ошибка получения постов {domain}: {e}")
			import traceback
			traceback.print_exc()
			return []

	def get_comments(self, owner_id, post_id):
		"""Получает комментарии к посту"""
		try:
			comments = self.vk.wall.getComments(
				owner_id=owner_id,
				post_id=post_id,
				count=100,
				preview_length=0,
				extended=0
			)['items']

			return comments

		except Exception as e:
			print(f"❌ Ошибка получения комментариев к посту {post_id}: {e}")
			return []

	def process_group(self, domain, keywords, days=7):
		"""Обрабатывает одну группу с улучшенным логированием"""
		print(f"🔍 Начинаем парсинг {domain}...")

		posts_count = 0
		comments_count = 0

		try:
			# Получаем или создаем источник
			source = self._get_or_create_source(domain)
			print(f"📋 Источник: {source.source_name}")

			# Получаем посты с расширенными ключевыми словами
			extended_keywords = keywords + [
				'тнс', 'энерго', 'энергосбыт',
				'тнсэнерго', 'тнс энерго', '#тнсэнерго', '#тнс_энерго'
			]

			posts = self.get_posts(domain, extended_keywords, days, count=200)
			print(f"📊 {domain}: найдено {len(posts)} постов")

			for post in posts:
				try:
					# Сохраняем пост
					saved_post = self._save_post(source, post, keywords)
					if not saved_post:
						continue

					posts_count += 1

					# Получаем комментарии
					comments = self.get_comments(post['owner_id'], post['id'])
					print(f"💬 Пост {post['id']}: {len(comments)} комментариев")

					for comment in comments:
						if comment.get('text'):
							sentiment = classify_text(comment['text'])

							# Сохраняем комментарий
							saved_comment = self._save_comment(saved_post, comment, sentiment)
							if saved_comment:
								comments_count += 1

								# Сохраняем негативные комментарии в JSON
								if sentiment == "Негативный комментарий":
									self._save_bad_comment(saved_post, comment, sentiment)

					# Коммитим после каждого поста
					with self.app.app_context():
						db.session.commit()

				except Exception as e:
					print(f"❌ Ошибка обработки поста {post.get('id')}: {e}")
					with self.app.app_context():
						db.session.rollback()
					continue

			print(f"✅ {domain}: сохранено {posts_count} постов, {comments_count} комментариев")
			return posts_count, comments_count

		except Exception as e:
			print(f"❌ Ошибка обработки группы {domain}: {e}")
			import traceback
			traceback.print_exc()
			return 0, 0

	def search_by_hashtag(self, domain, hashtag, days=7):
		"""Ищет посты по хештегу"""
		try:
			end_date = datetime.now()
			start_date = end_date - timedelta(days=days)
			start_timestamp = int(start_date.timestamp())

			# Получаем ID группы
			group_info = self.vk.utils.resolveScreenName(screen_name=domain)
			if not group_info or group_info['type'] != 'group':
				print(f"❌ Не удалось получить ID группы {domain}")
				return []

			group_id = -abs(group_info['object_id'])  # ID группы отрицательный

			# Ищем по хештегу
			response = self.vk.newsfeed.search(
				q=f"#{hashtag}",
				count=100,
				extended=1,
				start_time=start_timestamp
			)

			posts = []
			for item in response['items']:
				# Проверяем, что пост из нужной группы
				if item.get('owner_id') == group_id:
					posts.append(item)

			print(f"🔖 Найдено постов с #{hashtag} в {domain}: {len(posts)}")
			return posts

		except Exception as e:
			print(f"❌ Ошибка поиска по хештегу #{hashtag}: {e}")
			return []

	def _save_bad_comment(self, post, comment, sentiment):
		"""Сохраняет негативный комментарий в JSON"""
		try:
			bad_comments_path = os.path.join(root_dir, 'bad_comments.json')

			# Загружаем существующие комментарии
			if os.path.exists(bad_comments_path):
				with open(bad_comments_path, 'r', encoding='utf-8') as f:
					try:
						comments_list = json.load(f)
					except json.JSONDecodeError:
						comments_list = []
			else:
				comments_list = []

			# Проверяем на дубликаты
			comment_id = f"vk_{comment.get('id')}"
			exists = any(c.get('platform_comment_id') == comment_id for c in comments_list)

			if not exists:
				bad_comment_data = {
					'platform_comment_id': comment_id,
					'post_id': post.id,
					'post_title': post.text[:100] + '...' if post.text else 'Без названия',
					'post_url': post.url,
					'text': comment.get('text', ''),
					'user_id': str(comment.get('from_id', 'unknown')),
					'publish_date': datetime.fromtimestamp(comment.get('date', 0)).isoformat(),
					'platform': 'VK',
					'sentiment': sentiment,
					'platform_data': {
						'from_id': str(comment.get('from_id', 'unknown')),
						'likes': comment.get('likes', {}).get('count', 0)
					},
					'detection_date': datetime.now().isoformat()
				}

				comments_list.append(bad_comment_data)

				# Сохраняем обратно
				with open(bad_comments_path, 'w', encoding='utf-8') as f:
					json.dump(comments_list, f, ensure_ascii=False, indent=2)

				print(f"🔴 Негативный комментарий сохранен в JSON")

		except Exception as e:
			print(f"❌ Ошибка сохранения негативного комментария: {e}")

	def run(self, groups, keywords, days=7):
		"""Основной метод для запуска парсинга с улучшенным поиском"""
		print("🚀 Начинаем парсинг VK групп...")

		total_posts = 0
		total_comments = 0
		results = {}

		for group in groups:
			# Основной поиск по ключевым словам
			posts1, comments1 = self.process_group(group, keywords, days)

			# Дополнительный поиск по хештегам
			hashtag_posts = []
			for hashtag in ['тнсэнерго', 'тнс_энерго', 'тнс','ТНСэнергоНН']:
				posts_with_hashtag = self.search_by_hashtag(group, hashtag, days)
				hashtag_posts.extend(posts_with_hashtag)

			# Обрабатываем посты с хештегами
			if hashtag_posts:
				print(f"🔖 Обрабатываем {len(hashtag_posts)} постов с хештегами из {group}")
				source = self._get_or_create_source(group)
				additional_posts = 0
				additional_comments = 0

				for post in hashtag_posts:
					try:
						saved_post = self._save_post(source, post, keywords)
						if saved_post:
							additional_posts += 1
							# Получаем комментарии
							comments = self.get_comments(post['owner_id'], post['id'])
							additional_comments += len(comments)
					except:
						continue

				posts1 += additional_posts
				comments1 += additional_comments

			results[group] = {'posts': posts1, 'comments': comments1}
			total_posts += posts1
			total_comments += comments1

			# Пауза между группами
			time.sleep(1)

		# Выводим результаты
		print("\n" + "=" * 50)
		for group, stats in results.items():
			print(f"📁 {group}: {stats['posts']} постов, {stats['comments']} комментариев")

		print(f"\n🎯 ИТОГО сохранено в БД:")
		print(f"📊 Постов: {total_posts}")
		print(f"💬 Комментариев: {total_comments}")

		return results


def main():
	service = VKService()

	groups = [
		'tns_energo_nn',  # ТНС энерго НН
		'moynnov',  # Мой Нижний Новгород
		'governmentnnov',  # Правительство Нижегородской области
		'typical_nn'  # Типичный Нижний Новгород
	]

	keywords = [
		'тнс', 'энерго', 'энергосбыт',
	]

	results = service.run(groups, keywords, days=14)


if __name__ == '__main__':
	main()