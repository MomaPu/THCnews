import hashlib
from typing import List, Dict
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import time
import re
import json
import os
import tempfile

from app import create_app
from app.database import db
from app.models.models import NewsSource, NewsPost
from app.services.texteditor import classify_text
from app.bot.core import save_bad_comment


class OKServiceSelenium:
	def __init__(self):
		self.driver = None
		self.cookies_file = "ok_cookies.json"
		# Создаем Flask приложение
		self.app = create_app()
		self.setup_driver()

	def setup_driver(self):
		"""Настройка Chrome WebDriver"""
		print("🔄 Настройка Chrome WebDriver...")

		chrome_options = Options()
		chrome_options.add_argument("--no-sandbox")
		chrome_options.add_argument("--disable-dev-shm-usage")
		chrome_options.add_argument("--disable-gpu")
		chrome_options.add_argument("--window-size=1920,1080")
		chrome_options.add_argument("--disable-extensions")
		chrome_options.add_argument("--disable-notifications")

		chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
		chrome_options.add_experimental_option('useAutomationExtension', False)

		chrome_options.add_argument(
			"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

		try:
			service = Service(ChromeDriverManager().install())
			self.driver = webdriver.Chrome(service=service, options=chrome_options)
			self.driver.implicitly_wait(5)
			print("✅ Chrome успешно запущен")

		except Exception as e:
			print(f"❌ Ошибка запуска Chrome: {e}")
			raise

	def manual_login(self):
		"""Ручная авторизация"""
		print("=" * 60)
		print("РУЧНАЯ АВТОРИЗАЦИЯ")
		print("=" * 60)
		print("1. Браузер откроет страницу Одноклассников")
		print("2. Войдите в свой аккаунт вручную")
		print("3. После авторизации закройте всплывающие окна")
		print("4. Нажмите Enter в консоли чтобы продолжить...")
		print("=" * 60)

		self.driver.get("https://ok.ru")
		time.sleep(3)

		input("После авторизации нажмите Enter чтобы продолжить...")
		self.save_cookies()
		return True

	def save_cookies(self):
		"""Сохраняем cookies"""
		try:
			cookies = self.driver.get_cookies()
			with open(self.cookies_file, 'w', encoding='utf-8') as f:
				json.dump(cookies, f, ensure_ascii=False, indent=2)
			print("✅ Cookies сохранены")
		except Exception as e:
			print(f"❌ Ошибка сохранения cookies: {e}")

	def load_cookies(self):
		"""Загружаем сохраненные cookies"""
		try:
			if os.path.exists(self.cookies_file):
				with open(self.cookies_file, 'r', encoding='utf-8') as f:
					cookies = json.load(f)

				self.driver.get("https://ok.ru")
				time.sleep(2)
				self.driver.delete_all_cookies()

				for cookie in cookies:
					try:
						self.driver.add_cookie(cookie)
					except:
						continue

				print("✅ Cookies загружены")
				self.driver.refresh()
				time.sleep(3)
				return True
			return False
		except Exception as e:
			print(f"❌ Ошибка загрузки cookies: {e}")
			return False

	def is_logged_in(self):
		"""Проверяем авторизацию"""
		try:
			self.driver.get("https://ok.ru")
			time.sleep(2)

			try:
				WebDriverWait(self.driver, 5).until(
					EC.presence_of_element_located((By.CSS_SELECTOR, ".ucard-mini, .nav-side_i, [data-l='t,userPage']"))
				)
				print("✅ Авторизация подтверждена")
				return True
			except:
				current_url = self.driver.current_url
				if "login" in current_url or "auth" in current_url:
					return False
				return False

		except Exception as e:
			print(f"❌ Ошибка проверки авторизации: {e}")
			return False

	def ensure_logged_in(self):
		"""Убеждаемся, что авторизованы"""
		print("Проверяем авторизацию...")

		if self.load_cookies():
			if self.is_logged_in():
				print("✅ Авторизованы через cookies")
				return True

		print("❌ Требуется ручная авторизация")
		return self.manual_login()

	def _extract_comments_from_discussion_page(self, discussion_url, max_comments=50, wait_seconds=8):
		"""
		Открывает discussion_url в новой вкладке, парсит комментарии и закрывает вкладку.
		"""
		orig_handle = self.driver.current_window_handle
		comments = []

		try:
			# Открыть в новой вкладке
			self.driver.execute_script("window.open(arguments[0], '_blank');", discussion_url)
			time.sleep(2)

			# Переключиться на новую вкладку
			handles = self.driver.window_handles
			if len(handles) > 1:
				self.driver.switch_to.window(handles[-1])

				# Ждём загрузки
				time.sleep(3)

				# Пробуем разные селекторы для комментариев
				comment_selectors = [
					"div.comment_text",
					".comment-text",
					".comments_text",
					"[data-l='t,comment']",
					".textWrap",
					".d_comment_text"
				]

				for selector in comment_selectors:
					try:
						comment_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
						for el in comment_elements[:max_comments]:
							try:
								text = el.text.strip()
								if text and len(text) > 10:  # Минимальная длина комментария
									sentiment = classify_text(text)
									comments.append({
										'text': text,
										'sentiment': sentiment,
										'classified_text': f"[{sentiment}] {text}"
									})
							except:
								continue
						if comments:
							break
					except:
						continue

		except Exception as e:
			print(f"⚠ Не удалось загрузить комментарии: {e}")

		finally:
			try:
				# Закрываем вкладку обсуждения и возвращаемся
				if len(self.driver.window_handles) > 1:
					self.driver.close()
				self.driver.switch_to.window(orig_handle)
			except:
				pass

		# Очистка дублей
		cleaned = []
		seen = set()
		for comment in comments:
			text = comment['text'].strip()
			if text and text not in seen:
				cleaned.append(comment)
				seen.add(text)

		print(f'Найдено комментариев: {len(cleaned)}')
		return cleaned

	def save_post_to_db(self, post_data: dict, group_url: str):
		"""Сохраняет пост в базу данных"""
		with self.app.app_context():
			try:
				# Получаем или создаем источник
				source = NewsSource.query.filter_by(
					platform='ok',
					source_id=group_url
				).first()

				if not source:
					source = NewsSource(
						platform='ok',
						source_id=group_url,
						source_name=group_url.split('/')[-1],  # Берем только имя группы из URL
						source_type='group'
					)
					db.session.add(source)
					db.session.commit()  # Коммитим чтобы получить ID
					db.session.refresh(source)  # Обновляем объект

				# Создаем уникальный ID поста
				unique_content = f"{post_data.get('text', '')}_{post_data.get('url', '')}"
				post_id_str = hashlib.md5(unique_content.encode()).hexdigest()

				# Проверяем, существует ли уже пост
				existing_post = NewsPost.query.filter_by(
					platform='ok',
					platform_post_id=post_id_str
				).first()

				if not existing_post:
					post = NewsPost(
						platform='ok',
						platform_post_id=post_id_str,
						source_id=source.id,
						text=post_data.get('text', ''),
						url=post_data.get('url', ''),
						author=source.source_name,
						publish_date=datetime.now(),  # Можно парсить дату из поста если есть
						keywords=["ok", "соцсеть"],
						platform_data={
							'comments_count': len(post_data.get('comments', [])),
							'source_group': group_url,
							'original_date': post_data.get('date', '')
						}
					)
					db.session.add(post)
					db.session.commit()
					db.session.refresh(post)
					print(f"✅ Пост сохранен в БД: {post.id}")
					return post
				else:
					print(f"⚠️ Пост уже существует: {existing_post.id}")
					return existing_post

			except Exception as e:
				print(f"❌ Ошибка сохранения поста в БД: {e}")
				import traceback
				traceback.print_exc()
				db.session.rollback()
				return None

	def save_bad_comments_to_json(self, post, comments):
		"""Сохраняет негативные комментарии в JSON"""
		try:
			for comment in comments:
				if comment['sentiment'] == "Негативный комментарий":
					bad_comment_data = {
						'platform_comment_id': hashlib.md5(comment['text'].encode()).hexdigest(),
						'post_id': post.id,
						'post_title': post.text[:100] + '...' if post.text else 'Без названия',
						'post_url': post.url,
						'text': comment['text'],
						'user_id': 'anonymous',  # В OK нет информации о пользователе в комментариях
						'publish_date': datetime.now().isoformat(),
						'platform': 'OK',
						'sentiment': comment['sentiment'],
						'platform_data': {
							'source_group': post.platform_data.get('source_group', '')
						}
					}
					save_bad_comment(bad_comment_data)
		except Exception as e:
			print(f"Ошибка сохранения плохих комментариев: {e}")

	def get_group_posts(self, group_url: str, count: int = 10, max_scrolls: int = 6, max_comments_per_post: int = 20):
		"""
		Собирает посты из группы и сохраняет в БД
		"""
		if not self.is_logged_in():
			print("❌ Не авторизованы.")
			return []

		try:
			# Открываем группу
			self.driver.get(group_url)
			# Ждём появления постов
			WebDriverWait(self.driver, 12).until(
				EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed_cnt, div.feed_b, div.media-block"))
			)

			# Скроллим для подгрузки
			for i in range(max_scrolls):
				self.driver.execute_script("window.scrollBy(0, document.body.scrollHeight*0.6);")
				time.sleep(1.2)
				print(f"📜 Скролл {i + 1}/{max_scrolls}")

			posts_data = []
			seen_ids = set()

			# Находим контейнеры постов
			post_containers = self.driver.find_elements(By.CSS_SELECTOR, "div.feed_cnt, div.feed_b, div.media-block")
			print(f"Найдено контейнеров постов: {len(post_containers)}")

			for pc in post_containers[:count]:  # Ограничиваем количество обрабатываемых постов
				try:
					# Извлечение текста
					text = ""
					try:
						text_elements = pc.find_elements(By.CSS_SELECTOR,
														 ".media-text_cnt_tx, .media-text_cnt, .ugc__text, .feed-content, .feed_text")
						for el in text_elements:
							if el.text.strip():
								text = el.text.strip()
								break
						if not text:
							text = pc.text.strip()[:600]
					except:
						text = pc.text.strip()[:600]

					# Пропускаем пустые посты
					if not text or len(text) < 10:
						continue

					# Ссылка
					url = ""
					try:
						a = pc.find_element(By.CSS_SELECTOR, "a.media-text_a, a[href*='/topic/'], a[href*='/story/']")
						href = a.get_attribute("href")
						if href:
							url = href if href.startswith("http") else "https://ok.ru" + href
					except:
						url = ""

					# Дата
					date = ""
					try:
						time_el = pc.find_element(By.CSS_SELECTOR, "time")
						date = time_el.get_attribute("datetime") or time_el.text
					except:
						date = ""

					# Парсим комментарии
					comments = []
					try:
						comment_link = pc.find_element(By.CSS_SELECTOR,
													   "a[data-module='CommentWidgetsNew'], [data-module='CommentWidgetsNew']")
						href = comment_link.get_attribute("href") or ""
						if href:
							if href.startswith("/"):
								href = "https://ok.ru" + href
							comments = self._extract_comments_from_discussion_page(href,
																				   max_comments=max_comments_per_post)
					except Exception as e:
						# Пробуем альтернативные селекторы
						try:
							comment_links = pc.find_elements(By.CSS_SELECTOR,
															 "a[href*='comment'], a[href*='discussion']")
							for link in comment_links:
								href = link.get_attribute("href") or ""
								if href and ("comment" in href or "discussion" in href):
									if href.startswith("/"):
										href = "https://ok.ru" + href
									comments = self._extract_comments_from_discussion_page(href, max_comments=10)
									break
						except:
							pass

					# Фильтрация комментариев
					filtered_comments = []
					STOP_WORDS = {"комментировать", "коммент", "класс", "лайк", "поделиться", "ответить"}
					for comment in comments:
						text = comment['text'].strip()
						if not text or len(text) < 5:
							continue
						if any(stop_word in text.lower() for stop_word in STOP_WORDS):
							continue
						filtered_comments.append(comment)

					post_data = {
						"text": text,
						"url": url,
						"date": date,
						"comments": filtered_comments
					}

					# Сохраняем в БД
					saved_post = self.save_post_to_db(post_data, group_url)
					if saved_post:
						# Сохраняем негативные комментарии в JSON
						self.save_bad_comments_to_json(saved_post, filtered_comments)
						posts_data.append(post_data)
						print(f"📝 Обработан пост: {text[:50]}...")

				except Exception as ex:
					print(f"⚠ Ошибка при парсинге контейнера: {ex}")
					continue

			print(f"✅ Собрано постов: {len(posts_data)}")
			return posts_data

		except Exception as e:
			print(f"❌ Ошибка в get_group_posts: {e}")
			import traceback
			traceback.print_exc()
			return []

	def get_posts_from_groups(self,
							  group_urls: List[str],
							  per_group_count: int = 5,
							  total_limit: int = None,
							  delay_between_groups: float = 1.0,
							  max_scrolls: int = 6,
							  max_comments_per_post: int = 20,
							  tns_full_group_identifiers: List[str] = None,
							  keywords: List[str] = None) -> List[Dict]:

		if tns_full_group_identifiers is None:
			tns_full_group_identifiers = ["https://ok.ru/tnsenergon", "tnsenergon", "ok.ru/tnsenergon"]
		if keywords is None:
			keywords = ['ТНС энерго НН', 'ТНС энерго Нижний Новгород', 'ТНС',
					  'Энергосбыт Нижний Новгород', "ТНС Нижний"]

		all_posts = []
		seen_ids = set()
		seen_urls = set()
		seen_hashes = set()

		def is_tns_full_group(gurl: str) -> bool:
			low = gurl.lower()
			for ident in tns_full_group_identifiers:
				if ident.lower() in low:
					return True
			return False

		def text_contains_keyword(text: str) -> bool:
			if not text:
				return False
			low = text.lower()
			for kw in keywords:
				if kw.lower() in low:
					return True
			return False

		for idx, gurl in enumerate(group_urls):
			if total_limit and len(all_posts) >= total_limit:
				break

			print(f"⏳ Обработка группы {idx + 1}/{len(group_urls)}: {gurl}")
			try:
				group_posts = self.get_group_posts(
					group_url=gurl,
					count=per_group_count,
					max_scrolls=max_scrolls,
					max_comments_per_post=max_comments_per_post
				)
			except Exception as e:
				print(f"⚠ Ошибка при получении постов группы {gurl}: {e}")
				group_posts = []

			full_group = is_tns_full_group(gurl)
			group_posts_count = 0

			for p in group_posts:
				if total_limit and len(all_posts) >= total_limit:
					break

				post_id = p.get("id", "") or ""
				url = p.get("url", "") or ""
				text = p.get("text", "") or ""
				date = p.get("date", "") or ""

				# Пропускаем посты без текста и без URL
				if not text and not url:
					continue

				# Если это не "полная" группа — применяем текстовую фильтрацию
				if not full_group:
					if not text_contains_keyword(text):
						continue

				# Формируем ключ для дедупликации
				if post_id:
					key_type, key_val = "id", post_id
				elif url:
					key_type, key_val = "url", url
				else:
					key_type, key_val = "hash", hashlib.sha1(
						((text or "")[:300] + "|" + date).encode("utf-8")).hexdigest()

				is_dup = False
				if key_type == "id" and key_val in seen_ids:
					is_dup = True
				elif key_type == "url" and key_val in seen_urls:
					is_dup = True
				elif key_type == "hash" and key_val in seen_hashes:
					is_dup = True

				if is_dup:
					continue

				record = {
					"source_group": gurl,
					"id": post_id,
					"date": date,
					"text": text,
					"comments": [c['classified_text'] for c in p.get("comments", [])],
					"url": url
				}
				all_posts.append(record)
				group_posts_count += 1

				if key_type == "id":
					seen_ids.add(key_val)
				elif key_type == "url":
					seen_urls.add(key_val)
				else:
					seen_hashes.add(key_val)

			print(f"✅ Из группы {gurl} добавлено {group_posts_count} постов")
			time.sleep(delay_between_groups)

		print(f"✅ Всего собрано постов из всех групп: {len(all_posts)}")
		return all_posts

	def close(self):
		"""Закрытие драйвера"""
		if self.driver:
			self.driver.quit()
			print("✅ Браузер закрыт")


if __name__ == "__main__":
	groups = [
		"https://ok.ru/group/70000037422012",
		"https://ok.ru/tnsenergon",
		"https://ok.ru/kpnnovgorod",
		"https://ok.ru/newsnnru",
		"https://ok.ru/nizhegorodnosti"
	]

	service = OKServiceSelenium()
	try:
		if not service.ensure_logged_in():
			print("❌ Не удалось авторизоваться")
		else:
			posts = service.get_posts_from_groups(
				groups,
				per_group_count=5,
				total_limit=20,
				delay_between_groups=1.5,
				tns_full_group_identifiers=["https://ok.ru/tnsenergon", "tnsenergon"],
				keywords=['ТНС энерго НН', 'ТНС энерго Нижний Новгород', 'ТНС',
					  'Энергосбыт Нижний Новгород', "ТНС Нижний"]
			)

			for i, p in enumerate(posts, 1):
				print(f"{i}. {p['source_group']} - {p['url']} - {(p['text'] or '')[:120]}")
				if p['comments']:
					print(f"   Комментарии: {len(p['comments'])}")
	finally:
		service.close()