import vk_api
import asyncio
import aiohttp
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any


class VKService:
	def __init__(self, token):
		self.token = token
		self.vk = vk_api.VkApi(token=token)
		self.api = self.vk.get_api()
		self.session = None
		self.last_request_time = 0
		self.request_delay = 0.34  # ~3 запроса в секунду (VK limit)

	async def init_session(self):
		"""Инициализация aiohttp сессии"""
		self.session = aiohttp.ClientSession()

	async def close_session(self):
		"""Закрытие aiohttp сессии"""
		if self.session:
			await self.session.close()

	async def make_vk_request(self, method: str, params: dict) -> dict:
		"""Асинхронный запрос к VK API с задержкой"""
		if not self.session:
			await self.init_session()

		# Добавляем задержку между запросами
		current_time = time.time()
		time_since_last_request = current_time - self.last_request_time
		if time_since_last_request < self.request_delay:
			await asyncio.sleep(self.request_delay - time_since_last_request)

		params['access_token'] = self.token
		params['v'] = '5.131'

		url = f'https://api.vk.com/method/{method}'

		try:
			async with self.session.get(url, params=params) as response:
				data = await response.json()
				self.last_request_time = time.time()

				if 'error' in data:
					print(f"VK API Error: {data['error']}")
					return {}
				return data.get('response', {})
		except Exception as e:
			print(f"Request error: {e}")
			return {}

	async def get_company_news_async(self, company_domain: str, count: int = 10) -> List[Dict]:
		"""Асинхронно получаем новости компании"""
		try:
			data = await self.make_vk_request('wall.get', {
				'domain': company_domain,
				'count': count
			})
			posts = data.get('items', [])
			return [self._parse_post(p) for p in posts]
		except Exception as e:
			print(f"Ошибка при получении новостей {company_domain}: {e}")
			return []

	async def search_posts_async(self, group_domain: str, keywords: List[str],
								 days: int = 7, count: int = 100) -> List[Dict]:
		"""Асинхронный поиск постов по ключевым словам"""
		end_date = int(datetime.now().timestamp())
		start_date = int((datetime.now() - timedelta(days=days)).timestamp())

		try:
			data = await self.make_vk_request('wall.get', {
				'domain': group_domain,
				'count': count,
				'filter': 'all'
			})

			posts = data.get('items', [])
			found_posts = []

			for post in posts:
				if start_date <= post['date'] <= end_date:
					post_text = post.get('text', '').lower()
					if any(keyword.lower() in post_text for keyword in keywords):
						found_posts.append(self._parse_post(post))

			return found_posts

		except Exception as e:
			print(f"Ошибка при поиске постов {group_domain}: {e}")
			return []

	async def get_post_comments_async(self, owner_id: int, post_id: int,
									  count: int = 100, extended: bool = False) -> List[Dict]:
		"""Асинхронно получаем комментарии к посту"""
		try:
			data = await self.make_vk_request('wall.getComments', {
				'owner_id': owner_id,
				'post_id': post_id,
				'count': count,
				'extended': 1 if extended else 0,
				'need_likes': 1,
				'thread_items_count': 5
			})

			comments = data.get('items', [])
			parsed_comments = []

			for comment in comments:
				parsed_comment = self._parse_comment(comment)

				# Добавляем ответы на комментарии если они есть
				if 'thread' in comment and 'items' in comment['thread']:
					parsed_comment['replies'] = [
						self._parse_comment(reply) for reply in comment['thread']['items']
					]

				parsed_comments.append(parsed_comment)

			if extended and 'profiles' in data:
				profiles = {p['id']: p for p in data.get('profiles', [])}
				groups = {g['id']: g for g in data.get('groups', [])}

				for comment in parsed_comments:
					user_id = comment['from_id']
					if user_id > 0:
						comment['author'] = profiles.get(user_id, {})
						comment[
							'author_name'] = f"{comment['author'].get('first_name', '')} {comment['author'].get('last_name', '')}".strip()
					else:
						comment['author'] = groups.get(abs(user_id), {})
						comment['author_name'] = comment['author'].get('name', 'Группа')

			return parsed_comments

		except Exception as e:
			print(f"Ошибка при получении комментариев: {e}")
			return []

	async def get_posts_with_comments_async(self, group_domain: str, keywords: List[str] = None,
											days: int = 7, count: int = 100,
											comments_count: int = 5) -> List[Dict]:
		"""Асинхронно получаем посты с комментариями"""
		try:
			# Определяем тип парсинга для группы
			if group_domain == 'tns_energo_nn':
				posts = await self.get_company_news_async(group_domain, count)
			else:
				posts = await self.search_posts_async(group_domain, keywords or [], days, count)

			print(f"📊 {group_domain}: найдено {len(posts)} постов")

			# Последовательно получаем комментарии для каждого поста с задержкой
			for post in posts:
				if 'url' in post and 'wall' in post['url']:
					try:
						url_parts = post['url'].split('wall')[1].split('_')
						owner_id = int(url_parts[0])
						post_id = int(url_parts[1])

						post['comments'] = await self.get_post_comments_async(
							owner_id, post_id, comments_count, True
						)
						# Небольшая задержка между запросами комментариев
						await asyncio.sleep(0.1)

					except (ValueError, IndexError) as e:
						print(f"❌ Ошибка обработки URL поста {group_domain}: {e}")
						post['comments'] = []
				else:
					post['comments'] = []

			return posts

		except Exception as e:
			print(f"❌ Ошибка получения постов {group_domain}: {e}")
			return []

	async def parse_groups_sequentially(self) -> Dict[str, List[Dict]]:
		"""Парсим группы последовательно с задержками"""
		groups_config = {
			'tns_energo_nn': {
				'type': 'company',
				'keywords': None,
				'count': 20,
				'comments_count': 5
			},
			'moynnov': {
				'type': 'search',
				'keywords': ['энерг', 'свет', 'электрич', 'авария', 'ремонт'],
				'days': 30,
				'count': 30,
				'comments_count': 3
			},
			'governmentnnov': {
				'type': 'search',
				'keywords': ['энерг', 'коммунал', 'ЖКХ', 'инфраструктур'],
				'days': 30,
				'count': 30,
				'comments_count': 3
			},
			'typical_nn': {
				'type': 'search',
				'keywords': ['энерг', 'ТНС', 'счетчик', 'тариф'],
				'days': 30,
				'count': 30,
				'comments_count': 3
			},
			'chp_nn': {
				'type': 'search',
				'keywords': ['отоплен', 'тепло', 'авария', 'ремонт'],
				'days': 30,
				'count': 30,
				'comments_count': 3
			},
			'nnzhest': {
				'type': 'search',
				'keywords': ['жилищ', 'ЖКХ', 'коммунал', 'управляющ'],
				'days': 30,
				'count': 30,
				'comments_count': 3
			},
			'autono52': {
				'type': 'search',
				'keywords': ['транспорт', 'дорог', 'освещен', 'энерг'],
				'days': 30,
				'count': 30,
				'comments_count': 3
			}
		}

		final_results = {}

		for group_domain, config in groups_config.items():
			try:
				print(f"🔍 Начинаем парсинг {group_domain}...")

				if config['type'] == 'company':
					posts = await self.get_posts_with_comments_async(
						group_domain=group_domain,
						count=config['count'],
						comments_count=config['comments_count']
					)
				else:
					posts = await self.get_posts_with_comments_async(
						group_domain=group_domain,
						keywords=config['keywords'],
						days=config['days'],
						count=config['count'],
						comments_count=config['comments_count']
					)

				final_results[group_domain] = posts
				print(f"✅ {group_domain}: обработано {len(posts)} постов")

				# Задержка между группами
				await asyncio.sleep(1)

			except Exception as e:
				print(f"❌ Ошибка при парсинге {group_domain}: {e}")
				final_results[group_domain] = []

		return final_results

	def _parse_comment(self, comment_data):
		return {
			'id': comment_data.get('id'),
			'from_id': comment_data.get('from_id'),
			'date': datetime.fromtimestamp(comment_data.get('date', 0)).strftime('%Y-%m-%d %H:%M'),
			'text': comment_data.get('text', ''),
			'likes': comment_data.get('likes', {}).get('count', 0),
			'reply_to_user': comment_data.get('reply_to_user'),
			'reply_to_comment': comment_data.get('reply_to_comment')
		}

	def _parse_post(self, post_data):
		return {
			'id': post_data.get('id'),
			'text': post_data.get('text', ''),
			'date': datetime.fromtimestamp(post_data.get('date', 0)).strftime('%Y-%m-%d %H:%M'),
			'url': f"https://vk.com/wall{post_data.get('owner_id', 0)}_{post_data.get('id', 0)}",
			'likes': post_data.get('likes', {}).get('count', 0),
			'reposts': post_data.get('reposts', {}).get('count', 0),
			'views': post_data.get('views', {}).get('count', 0) if 'views' in post_data else 0
		}


async def main():
	# Инициализация сервиса
	vk_service = VKService(token='5746854757468547574685473b547eebd055746574685473fdcc76d76189e0967f0739b')

	try:
		# Парсим группы последовательно с задержками
		print("🚀 Начинаем парсинг всех групп...")
		results = await vk_service.parse_groups_sequentially()

		# Вывод результатов
		total_posts = 0
		total_comments = 0

		for group_domain, posts in results.items():
			print(f"\n{'=' * 60}")
			print(f"📁 ГРУППА: {group_domain}")
			print(f"📊 Найдено постов: {len(posts)}")

			group_comments = 0
			for i, post in enumerate(posts[:3], 1):  # Показываем первые 3 поста
				post_comments = len(post.get('comments', []))
				group_comments += post_comments

				print(f"\n  📝 Пост #{i} [{post['date']}]")
				print(f"  ❤️ Лайков: {post['likes']} | 🔄 Репостов: {post['reposts']}")
				print(f"  📄 Текст: {post['text'][:100]}...")
				print(f"  🔗 URL: {post['url']}")
				print(f"  💬 Комментариев: {post_comments}")

				# Показываем первые 2 комментария
				for j, comment in enumerate(post.get('comments', [])[:2], 1):
					author = comment.get('author_name', f"user{comment['from_id']}")
					print(f"    💭 {j}. [{author}]: {comment['text'][:50]}...")

			total_posts += len(posts)
			total_comments += group_comments
			print(f"  💬 Всего комментариев в группе: {group_comments}")

		print(f"\n🎯 ИТОГО:")
		print(f"📊 Постов: {total_posts}")
		print(f"💬 Комментариев: {total_comments}")

	finally:
		await vk_service.close_session()


if __name__ == "__main__":
	asyncio.run(main())