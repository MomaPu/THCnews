from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
import time
import re


class OKServiceSelenium:
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
		chrome_options.experimental_options["prefs"] = {
			"profile.managed_default_content_settings.javascript": 2
		}
		chrome_options.add_experimental_option(
			"prefs", {
				# block image loading
				"profile.managed_default_content_settings.images": 2,
			}
		)
		chrome_options.add_argument(
			"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

		# Используем webdriver-manager для автоматической загрузки драйвера
		service = Service(ChromeDriverManager().install())
		self.driver = webdriver.Chrome(service=service, options=chrome_options)
		self.driver.implicitly_wait(15)

	def get_group_posts(self, group_url, count=10):
		"""Получение постов из группы через Selenium"""
		try:
			print(f"Открываем страницу группы: {group_url}")
			self.driver.get(group_url)

			# Даем время для загрузки страницы
			time.sleep(5)

			# Ждем загрузки хотя бы каких-то элементов
			WebDriverWait(self.driver, 20).until(
				EC.presence_of_element_located((By.TAG_NAME, "body"))
			)

			# Прокручиваем страницу для загрузки большего количества постов
			for i in range(3):
				self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
				print(f"Прокрутка {i + 1}/3...")
				time.sleep(3)

			# Ищем посты по различным возможным селекторам
			possible_selectors = [
				"[data-l='t,mediaTopic']",
				".media-topic",
				".feed_w",
				".feed",
				".post",
				".topic",
				".group-feed",
				"[class*='feed']",
				"[class*='post']",
				"[class*='topic']"
			]

			posts = []
			for selector in possible_selectors:
				try:
					found_posts = self.driver.find_elements(By.CSS_SELECTOR, selector)
					if found_posts:
						print(f"Найдено {len(found_posts)} постов с селектором: {selector}")
						posts = found_posts
						break
				except:
					continue

			if not posts:
				print("Посты не найдены. Попробуем найти любой контент...")
				# Попробуем найти любые элементы с текстом
				all_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '')]")
				text_elements = [el for el in all_elements if len(el.text.strip()) > 50]
				posts = text_elements[:count]

			parsed_posts = []

			for i, post in enumerate(posts[:count]):
				try:
					print(f"Парсим пост {i + 1}...")
					post_data = self._parse_post_element(post)
					if post_data and post_data['text'].strip():
						# Получаем ID поста для получения комментариев
						post_id = self._get_post_id(post)
						post_data['post_id'] = post_id
						post_data['element'] = post  # Сохраняем элемент для клика
						parsed_posts.append(post_data)
						print(f"Успешно распарсен пост: {post_data['text'][:50]}...")
				except Exception as e:
					print(f"Ошибка парсинга поста {i + 1}: {e}")
					continue

			return parsed_posts

		except Exception as e:
			print(f"Ошибка при получении постов: {e}")
			return []

	def _get_post_id(self, post_element):
		"""Получаем ID поста из атрибутов элемента"""
		try:
			# Пробуем разные атрибуты для получения ID
			for attr in ['data-id', 'id', 'data-l', 'data-uid']:
				try:
					post_id = post_element.get_attribute(attr)
					if post_id and len(post_id) > 5:
						return post_id
				except:
					continue
			return ""
		except:
			return ""

	def _parse_post_element(self, post_element):
		"""Парсинг элемента поста"""
		try:
			# Получаем весь текст элемента и его дочерних элементов
			text = post_element.text.strip()

			# Ищем дату в тексте (эвристический подход)
			date_patterns = [
				r'\d{1,2}\s+\w+\s+\d{4}',
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

			# Извлекаем ссылку если есть
			try:
				link = post_element.find_element(By.TAG_NAME, "a").get_attribute("href")
			except:
				link = ""

			# Пытаемся найти лайки и комментарии
			likes = 0
			comments = 0

			# Ищем числа в тексте, которые могут быть лайками/комментариями
			numbers = re.findall(r'\b\d+\b', text)
			if numbers:
				# Берем последние два числа как возможные лайки и комментарии
				numbers = list(map(int, numbers))
				if len(numbers) >= 2:
					likes, comments = numbers[-2], numbers[-1]
				elif numbers:
					likes = numbers[-1]

			return {
				'text': text,
				'date': date_str or datetime.now().strftime('%Y-%m-%d %H:%M'),
				'likes': likes,
				'comments': comments,
				'url': link
			}

		except Exception as e:
			print(f"Ошибка детального парсинга: {e}")
			return None

	def search_posts_with_keyword(self, group_url, keyword, count=5):
		"""Поиск постов с определенным ключевым словом"""
		print(f"Ищем посты с ключевым словом: '{keyword}'")
		posts = self.get_group_posts(group_url, count=20)

		if not posts:
			print("Посты не найдены")
			return []

		found_posts = []
		for post in posts:
			post_text = post.get('text', '').lower()
			if keyword.lower() in post_text:
				print(f"Найден пост с ключевым словом '{keyword}': {post['text'][:50]}...")
				found_posts.append(post)

		print(f"Найдено {len(found_posts)} постов с ключевым словом '{keyword}'")
		return found_posts[:count]

	def get_post_comments(self, post_element):
		"""Получение комментариев к посту"""
		try:
			# Пытаемся найти кнопку комментариев и кликнуть
			comment_buttons = post_element.find_elements(By.XPATH,
														 ".//*[contains(text(), 'Комментировать') or contains(text(), 'комментари')]")

			if comment_buttons:
				print("Находим кнопку комментариев...")
				comment_buttons[0].click()
				time.sleep(3)

				# Ждем загрузки комментариев
				time.sleep(2)

				# Ищем комментарии
				comment_selectors = [
					".comment",
					".comment-item",
					"[data-l='t,comment']",
					".media-comment"
				]

				comments = []
				for selector in comment_selectors:
					try:
						comment_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
						if comment_elements:
							print(f"Найдено {len(comment_elements)} комментариев")
							for comment_element in comment_elements:
								comment_text = comment_element.text.strip()
								if comment_text and len(comment_text) > 5:
									comments.append(comment_text)
							break
					except:
						continue

				return comments
			else:
				print("Кнопка комментариев не найдена")
				return []

		except Exception as e:
			print(f"Ошибка при получении комментариев: {e}")
			return []

	def get_posts_with_comments(self, group_url, keyword="ТНС", count=3):
		"""Получаем посты с ключевым словом и их комментарии"""
		# Ищем посты с ключевым словом
		target_posts = self.search_posts_with_keyword(group_url, keyword, count)

		if not target_posts:
			print(f"Посты с ключевым словом '{keyword}' не найдены")
			return []

		results = []

		for i, post in enumerate(target_posts):
			print(f"\nОбрабатываем пост {i + 1}:")
			print(f"Текст: {post['text'][:100]}...")

			# Прокручиваем к посту
			try:
				self.driver.execute_script("arguments[0].scrollIntoView();", post['element'])
				time.sleep(2)
			except:
				pass

			# Получаем комментарии
			comments = self.get_post_comments(post['element'])

			results.append({
				'post': post,
				'comments': comments
			})

			print(f"Найдено {len(comments)} комментариев к посту")

		return results

	def close(self):
		"""Закрытие драйвера"""
		if self.driver:
			self.driver.quit()


# Основная функция для поиска постов с "ТНС" и комментариями
def find_tns_posts_with_comments(group_url):
	"""Поиск постов с 'ТНС' и их комментариев"""
	ok_service = OKServiceSelenium()

	try:
		print("=" * 60)
		print(f"ПОИСК ПОСТОВ С 'ТНС' В ГРУППЕ")
		print("=" * 60)

		# Ищем посты с "ТНС" и получаем комментарии
		results = ok_service.get_posts_with_comments(group_url, "открыли", count=5)

		if not results:
			print("\n❌ Посты с ключевым словом 'ТНС' не найдены")
			return

		print("\n" + "=" * 60)
		print("РЕЗУЛЬТАТЫ ПОИСКА:")
		print("=" * 60)

		for i, result in enumerate(results, 1):
			post = result['post']
			comments = result['comments']

			print(f"\n📝 ПОСТ {i}:")
			print(f"📅 Дата: {post['date']}")
			print(f"❤️  Лайков: {post['likes']}")
			print(f"💬 Комментариев: {post['comments']}")
			print(f"🔗 Ссылка: {post['url']}")
			print(f"📄 Текст:\n{post['text']}")

			print(f"\n💬 КОММЕНТАРИИ ({len(comments)}):")
			if comments:
				for j, comment in enumerate(comments[:10], 1):  # Показываем первые 10 комментариев
					print(f"  {j}. {comment[:100]}...")
			else:
				print("  Комментарии не найдены")

			print("-" * 40)

		print(f"\n✅ Найдено {len(results)} постов с ключевым словом 'ТНС'")

	except Exception as e:
		print(f"❌ Ошибка: {e}")
	finally:
		ok_service.close()


# Пример использования
if __name__ == "__main__":
	# Замените на URL вашей группы
	GROUP_URL = "https://ok.ru/group/70000037422012"  # Пример публичной группы

	# Ищем посты с "ТНС" и их комментарии
	find_tns_posts_with_comments(GROUP_URL)