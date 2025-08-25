from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import time
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse


class BrowserServiceSelenium:
	def __init__(self):
		self.driver = None
		self.setup_driver()

	def setup_driver(self):
		"""Настройка Chrome WebDriver с webdriver-manager"""
		chrome_options = Options()
		chrome_options.add_argument("--disable-gpu")
		chrome_options.add_argument("--no-sandbox")
		chrome_options.add_argument("--disable-dev-shm-usage")
		chrome_options.add_argument("--disable-blink-features=AutomationControlled")
		chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
		chrome_options.add_experimental_option('useAutomationExtension', False)
		chrome_options.add_argument("--window-size=1920,1080")
		chrome_options.add_argument("--headless")  # Добавляем headless режим для скорости

		chrome_options.add_argument(
			"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

		service = Service(ChromeDriverManager().install())
		self.driver = webdriver.Chrome(service=service, options=chrome_options)
		self.driver.implicitly_wait(5)  # Уменьшаем время ожидания

	def get_posts_from_site(self, url):
		"""Универсальный метод для получения постов с разных сайтов"""
		print(f"Парсим сайт: {url}")

		# Определяем тип сайта и используем соответствующий парсер
		domain = urlparse(url).netloc

		if 'kp.ru' in domain:
			return self._parse_kp_ru(url)
		elif 'aif.ru' in domain:
			return self._parse_aif_ru(url)
		elif 'mk.ru' in domain:
			return self._parse_mk_ru(url)
		elif 'dzen.ru' in domain:
			return self._parse_dzen(url)
		else:
			return self._parse_generic_site(url)


	def _parse_kp_ru(self, url):
		"""Парсер для kp.ru"""
		print("Используем парсер для kp.ru")
		self.driver.get(url)
		time.sleep(3)

		# Специфичные селекторы для kp.ru
		selectors = [
			"article",
			".sc-1tputnk-3",  # Специфичные классы kp.ru
			".sc-1tputnk-8",
			".sc-1tputnk-2",
			"[data-l='t,mediaTopic']",
			".media-topic",
			".feed_w",
			".post",
			".topic"
		]

		return self._find_and_parse_elements(selectors)

	def _parse_aif_ru(self, url):
		"""Парсер для aif.ru"""
		print("Используем парсер для aif.ru")
		self.driver.get(url)
		time.sleep(3)

		# Специфичные селекторы для aif.ru
		selectors = [
			"article",
			".article",
			".news_item",
			".b-article",
			".item",
			"[data-type='article']",
			".js-article-item",
			".rubric_news_list_item"
		]

		return self._find_and_parse_elements(selectors)

	def _parse_mk_ru(self, url):
		"""Парсер для mk.ru"""
		print("Используем парсер для mk.ru")
		self.driver.get(url)
		time.sleep(3)

		# Специфичные селекторы для mk.ru
		selectors = [
			".news-listing__item",
			".article",
			".news-item",
			".listing-item",
			".item",
			"[data-article]",
			"article",
			".news-block"
		]

		return self._find_and_parse_elements(selectors)

	def _parse_generic_site(self, url):
		"""Универсальный парсер для других сайтов"""
		print("Используем универсальный парсер")
		self.driver.get(url)
		time.sleep(3)

		# Общие селекторы для новостных сайтов
		selectors = [
			"article",
			".article",
			".news-item",
			".post",
			".item",
			".card",
			"[data-id]",
			".story",
			".news"
		]

		return self._find_and_parse_elements(selectors)

	def _parse_dzen(self, url):
		"""Парсер для dzen"""
		print("Используем парсер для dzen")
		self.driver.get(url)
		time.sleep(4)

		# Более специфичные селекторы для Dzen - ограничиваем количество
		selectors = [
			# Самые специфичные селекторы first
			"[data-testid='news-item']",
			"[data-testid='news-card']",
			"[data-testid='card-news']",
			".news-card",
			".news-item",
			"[role='article']",
			"article"
		]

		# Сначала пробуем самые специфичные селекторы
		posts = self._find_and_parse_elements(selectors)

		# Если нашли достаточно постов, возвращаем
		if len(posts) >= 10:
			print(f"Найдено {len(posts)} постов через специфичные селекторы")
			return posts

		# Если мало постов, пробуем более общие селекторы с ограничением
		print("Пробуем дополнительные селекторы с ограничением...")

		additional_selectors = [
			"[data-testid*='news']",
			"[data-testid*='card']",
			"[class*='news-card']",
			"[class*='news-item']"
		]

		for selector in additional_selectors:
			try:
				elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
				if elements:
					print(f"Найдено {len(elements)} элементов с: {selector}")
					# Берем только первые 20 элементов чтобы не перегружать
					limited_elements = elements[:20]
					text_elements = [el for el in limited_elements if el.text.strip() and len(el.text.strip()) > 30]

					for element in text_elements:
						try:
							parsed_post = self._parse_post_element(element)
							if parsed_post and parsed_post['text']:
								posts.append(parsed_post)
						except:
							continue

					if len(posts) >= 15:  # Если набрали достаточно постов
						break

			except Exception as e:
				continue

		print(f"Успешно распаршено {len(posts)} постов с Dzen")
		return posts

	def _find_and_parse_elements(self, selectors):
		"""Поиск и парсинг элементов по селекторам"""
		posts = []

		# Прокручиваем немного для загрузки контента
		self.driver.execute_script("window.scrollTo(0, 500);")
		time.sleep(1)

		for selector in selectors:
			try:
				elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
				if elements:
					print(f"Найдено {len(elements)} элементов с селектором: {selector}")
					# Более либеральный фильтр по длине текста
					text_elements = [el for el in elements if el.text.strip() and len(el.text.strip()) > 30]
					if text_elements:
						posts.extend(text_elements)
			except Exception as e:
				continue

		# Если не нашли достаточно элементов, пробуем найти по тексту
		if len(posts) < 5:
			try:
				all_elements = self.driver.find_elements(By.XPATH, "//*[string-length(text()) > 50]")
				posts.extend(all_elements[:10])
			except:
				pass

		# Парсим найденные посты
		parsed_posts = []
		for post_element in posts:
			try:
				parsed_post = self._parse_post_element(post_element)
				if parsed_post and parsed_post['text']:
					parsed_posts.append(parsed_post)
			except Exception as e:
				continue

		print(f"Успешно распаршено {len(parsed_posts)} постов")
		return parsed_posts

	def _parse_post_element(self, post_element):
		try:
			text = post_element.text.strip()

			if not text or len(text) < 30:
				return None

			# Ищем дату
			date_patterns = [
				r'\d{1,2}\s+[а-я]+\s+\d{4}',
				r'\d{1,2}\.\d{1,2}\.\d{4}',
				r'\d{1,2}:\d{2}',
				r'вчера',
				r'сегодня',
				r'\d+\s+минут',
				r'\d+\s+час',
			]

			date_str = ""
			for pattern in date_patterns:
				match = re.search(pattern, text, re.IGNORECASE)
				if match:
					date_str = match.group()
					break

			# Ищем ссылку
			link = ""
			try:
				# Ищем ссылку в элементе и его родителях
				current = post_element
				for _ in range(3):
					try:
						links = current.find_elements(By.TAG_NAME, "a")
						for link_element in links:
							href = link_element.get_attribute("href")
							if href and href.startswith('http'):
								link = href
								break
						if link:
							break
					except:
						pass
					current = current.find_element(By.XPATH, "./..")
			except:
				pass

			return {
				'text': text,
				'date': date_str or datetime.now().strftime('%Y-%m-%d %H:%M'),
				'url': link or self.driver.current_url,
				'source': self.driver.current_url
			}

		except Exception as e:
			return None

	def search_posts_with_keyword(self, url, keyword, count=5):
		"""Поиск постов с определенным ключевым словом"""
		print(f"Ищем посты с ключевым словом: '{keyword}'")
		posts = self.get_posts_from_site(url)

		if not posts:
			print("Посты не найдены")
			return []

		found_posts = []
		for post in posts:
			post_text = post.get('text', '').lower()
			if keyword.lower() in post_text:
				found_posts.append(post)

		print(f"Найдено {len(found_posts)} постов с ключевым словом '{keyword}'")
		return found_posts[:count]

	def get_posts(self, url, keyword, count=3):
		"""Алиас для search_posts_with_keyword"""
		return self.search_posts_with_keyword(url, keyword, count)

	def close(self):
		"""Закрытие драйвера"""
		if self.driver:
			self.driver.quit()


class AsyncNewsParser:
	"""Класс для асинхронного парсинга нескольких сайтов"""

	def __init__(self):
		self.executor = ThreadPoolExecutor(max_workers=3)

	async def parse_site_async(self, url, keyword, count=3):
		"""Асинхронный парсинг одного сайта"""
		loop = asyncio.get_event_loop()

		try:
			result = await loop.run_in_executor(
				self.executor,
				self._parse_site_sync,
				url, keyword, count
			)
			return result
		except Exception as e:
			print(f"Ошибка при парсинге {url}: {e}")
			return {'url': url, 'posts': [], 'count': 0}

	def _parse_site_sync(self, url, keyword, count):
		"""Синхронный метод для парсинга"""
		service = BrowserServiceSelenium()
		try:
			posts = service.search_posts_with_keyword(url, keyword, count)
			return {
				'url': url,
				'posts': posts,
				'count': len(posts)
			}
		except Exception as e:
			print(f"Ошибка в синхронном парсинге {url}: {e}")
			return {'url': url, 'posts': [], 'count': 0}
		finally:
			service.close()

	async def parse_multiple_sites(self, sites_keywords, count=3):
		"""Парсинг нескольких сайтов одновременно"""
		tasks = []

		for site_info in sites_keywords:
			url = site_info['url']
			keyword = site_info['keyword']
			task = self.parse_site_async(url, keyword, count)
			tasks.append(task)

		results = await asyncio.gather(*tasks, return_exceptions=True)

		valid_results = []
		for result in results:
			if isinstance(result, dict) and 'posts' in result:
				valid_results.append(result)

		return valid_results

	def close(self):
		"""Закрытие executor"""
		self.executor.shutdown()


async def async_parse_news_sites():
	"""Асинхронный парсинг нескольких новостных сайтов"""
	parser = AsyncNewsParser()

	# Список сайтов и ключевых слов для поиска
	sites_to_parse = [
		{'url': 'https://www.nnov.kp.ru/online/', 'keyword': 'Путин'},
		{'url': 'https://nn.aif.ru/', 'keyword': 'Путин'},
		{'url': 'https://nn.mk.ru/', 'keyword': 'Путин'},
		{'url': 'https://dzen.ru/news/region/nizhny_novgorod', 'keyword': 'Владимир'}
	]

	try:
		print("=" * 60)
		print("🔄 АСИНХРОННЫЙ ПАРСИНГ НОВОСТНЫХ САЙТОВ")
		print("=" * 60)

		start_time = time.time()
		results = await parser.parse_multiple_sites(sites_to_parse, count=4)
		end_time = time.time()

		print(f"⏱ Общее время выполнения: {end_time - start_time:.2f} секунд")
		print("\n" + "=" * 60)
		print("📊 РЕЗУЛЬТАТЫ АСИНХРОННОГО ПАРСИНГА:")
		print("=" * 60)

		total_posts = 0
		print("\n" + "=" * 60)
		print("📊 РЕЗУЛЬТАТЫ АСИНХРОННОГО ПАРСИНГА:")
		print("=" * 60)

		total_posts = 0
		for result in results:
			print(f"\n🌐 Сайт: {result['url']}")
			print(f"📈 Найдено постов: {result['count']}")

			if result['count'] > 0:
				for i, post in enumerate(result['posts'][:3], 1):  # Показываем первые 3 поста
					print(f"\n   📝 Пост {i}:")
					print(f"   📅 Дата: {post['date']}")
					print(f"   🔗 Ссылка: {post['url'][:70]}...")
					print(f"   📄 Текст: {post['text'][:120]}...")
					print("   " + "-" * 40)
			else:
				print("   ❌ Посты не найдены")

			total_posts += result['count']

		print(f"\n✅ Всего найдено постов на всех сайтах: {total_posts}")
	finally:
		parser.close()


def sync_parse_single_site(url, keyword="новости", count=3):
	"""Синхронный парсинг одного сайта"""
	service = BrowserServiceSelenium()

	try:
		print("=" * 60)
		print(f"🔄 ПАРСИНГ САЙТА: {url}")
		print("=" * 60)

		results = service.search_posts_with_keyword(url, keyword, count)

		print(f"\n📊 Результаты для {url}:")
		for i, post in enumerate(results, 1):
			print(f"\n📝 Пост {i}:")
			print(f"📅 Дата: {post['date']}")
			print(f"🔗 Ссылка: {post['url'][:50]}...")
			print(f"📄 Текст: {post['text'][:100]}...")

	finally:
		service.close()


# Пример использования
if __name__ == "__main__":
	# Вариант 1: Асинхронный парсинг всех сайтов
	asyncio.run(async_parse_news_sites())

	print("\n" + "=" * 80)

