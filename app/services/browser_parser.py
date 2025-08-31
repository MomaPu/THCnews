import hashlib
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
from urllib.parse import urlparse
from typing import List, Dict, Optional
from app import create_app
from app.database import db
from app.models.models import NewsSource, NewsPost


class WebParserSelenium:
    def __init__(self):
        self.driver = None
        # Создаем Flask приложение
        self.app = create_app()
        self.setup_driver()
        # Ключевые слова для поиска
        self.keywords = ['ТНС энерго НН', 'ТНС энерго Нижний Новгород', 'ТНС',
					  'Энергосбыт Нижний Новгород', "ТНС Нижний"]

    def setup_driver(self):
        """Настройка Chrome WebDriver"""
        chrome_options = Options()
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--headless")

        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.implicitly_wait(5)
            print("✅ Веб-парсер инициализирован")
        except Exception as e:
            print(f"❌ Ошибка инициализации веб-парсера: {e}")
            raise

    def _contains_keywords(self, text: str) -> bool:
        """Проверяет, содержит ли текст ключевые слова"""
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.keywords)

    def save_post_to_db(self, post_data: dict, source_url: str):
        """Сохраняет пост в базу данных"""
        with self.app.app_context():
            try:
                # Проверяем, содержит ли пост ключевые слова
                if not self._contains_keywords(post_data.get('text', '')):
                    return False

                # Получаем или создаем источник
                source = NewsSource.query.filter_by(
                    platform='web',
                    source_id=source_url
                ).first()

                if not source:
                    source_name = urlparse(source_url).netloc
                    source = NewsSource(
                        platform='web',
                        source_id=source_url,
                        source_name=source_name,
                        source_type='website'
                    )
                    db.session.add(source)
                    db.session.flush()

                # Проверяем, существует ли уже пост
                post_hash = hashlib.md5(post_data['text'].encode()).hexdigest()
                existing_post = NewsPost.query.filter_by(
                    platform='web',
                    platform_post_id=post_hash
                ).first()

                if not existing_post:
                    post = NewsPost(
                        platform='web',
                        platform_post_id=post_hash,
                        source_id=source.id,
                        text=post_data.get('text', ''),
                        url=post_data.get('url', ''),
                        author=source.source_name,
                        publish_date=datetime.now(),
                        platform_data={
                            'source': source_url,
                            'date_str': post_data.get('date', ''),
                            'original_source': post_data.get('source', '')
                        }
                    )
                    db.session.add(post)
                    db.session.commit()
                    print(f"✅ Сохранен пост с ключевыми словами: {post_data.get('text', '')[:50]}...")
                    return True
                return False

            except Exception as e:
                print(f"Ошибка сохранения поста в БД: {e}")
                db.session.rollback()
                return False

    def get_posts_data(self, url: str, count: int = 5) -> List[Dict]:
        """Универсальный метод для получения постов с разных сайтов с сохранением в БД"""
        print(f"🌐 Парсим сайт: {url}")
        print(f"🔍 Ищем ключевые слова: {', '.join(self.keywords)}")

        # Определяем тип сайта
        domain = urlparse(url).netloc

        if 'kp.ru' in domain:
            posts = self._parse_kp_ru(url, count)
        elif 'aif.ru' in domain:
            posts = self._parse_aif_ru(url, count)
        elif 'mk.ru' in domain:
            posts = self._parse_mk_ru(url, count)
        elif 'dzen.ru' in domain:
            posts = self._parse_dzen(url, count)
        else:
            posts = self._parse_generic_site(url, count)

        # Фильтруем по ключевым словам и сохраняем в БД
        filtered_posts = []
        for post in posts:
            if self._contains_keywords(post.get('text', '')):
                filtered_posts.append(post)

        # Сохраняем отфильтрованные посты в БД
        saved_posts = []
        for post in filtered_posts:
            if self.save_post_to_db(post, url):
                saved_posts.append(post)

        print(f"✅ Найдено {len(filtered_posts)} постов с ключевыми словами")
        print(f"✅ Сохранено в БД: {len(saved_posts)} постов")
        return saved_posts

    def _parse_kp_ru(self, url: str, count: int) -> List[Dict]:
        """Парсер для kp.ru"""
        print("📰 Используем парсер для kp.ru")
        self.driver.get(url)
        time.sleep(3)

        selectors = [
            "article", ".sc-1tputnk-3", ".sc-1tputnk-8",
            ".sc-1tputnk-2", "[data-l='t,mediaTopic']",
            ".media-topic", ".feed_w", ".post", ".topic"
        ]

        return self._find_and_parse_elements(selectors, count, url)

    def _parse_aif_ru(self, url: str, count: int) -> List[Dict]:
        """Парсер для aif.ru"""
        print("📰 Используем парсер для aif.ru")
        self.driver.get(url)
        time.sleep(3)

        selectors = [
            "article", ".article", ".news_item", ".b-article",
            ".item", "[data-type='article']", ".js-article-item",
            ".rubric_news_list_item"
        ]

        return self._find_and_parse_elements(selectors, count, url)

    def _parse_mk_ru(self, url: str, count: int) -> List[Dict]:
        """Парсер для mk.ru"""
        print("📰 Используем парсер для mk.ru")
        self.driver.get(url)
        time.sleep(3)

        selectors = [
            ".news-listing__item", ".article", ".news-item",
            ".listing-item", ".item", "[data-article]", "article", ".news-block"
        ]

        return self._find_and_parse_elements(selectors, count, url)

    def _parse_dzen(self, url: str, count: int) -> List[Dict]:
        """Парсер для dzen"""
        print("📰 Используем парсер для dzen")
        self.driver.get(url)
        time.sleep(4)

        selectors = [
            "[data-testid='news-item']", "[data-testid='news-card']",
            "[data-testid='card-news']", ".news-card",
            ".news-item", "[role='article']", "article"
        ]

        posts = self._find_and_parse_elements(selectors, count, url)

        if len(posts) >= count:
            return posts

        # Дополнительные селекторы
        additional_selectors = [
            "[data-testid*='news']", "[data-testid*='card']",
            "[class*='news-card']", "[class*='news-item']"
        ]

        for selector in additional_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements[:10]:
                    post_data = self._parse_post_element(element, url)
                    if post_data:
                        posts.append(post_data)
                        if len(posts) >= count:
                            break
                if len(posts) >= count:
                    break
            except:
                continue

        return posts[:count]

    def _parse_generic_site(self, url: str, count: int) -> List[Dict]:
        """Универсальный парсер для других сайтов"""
        print("📰 Используем универсальный парсер")
        self.driver.get(url)
        time.sleep(3)

        selectors = [
            "article", ".article", ".news-item", ".post",
            ".item", ".card", "[data-id]", ".story", ".news"
        ]

        return self._find_and_parse_elements(selectors, count, url)

    def _find_and_parse_elements(self, selectors: List[str], count: int, source_url: str) -> List[Dict]:
        """Поиск и парсинг элементов по селекторам"""
        posts = []
        try:
            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(1)

            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        post_data = self._parse_post_element(element, source_url)
                        if post_data:
                            posts.append(post_data)
                            if len(posts) >= count:
                                break
                    if len(posts) >= count:
                        break
                except:
                    continue
        except Exception as e:
            print(f"⚠ Ошибка при парсинге: {e}")

        return posts[:count]

    def _parse_post_element(self, post_element, source_url: str) -> Optional[Dict]:
        try:
            text = post_element.text.strip()
            if not text or len(text) < 50:
                return None

            # Ищем дату
            date_str = ""
            date_patterns = [
                r'\d{1,2}\s+[а-я]+\s+\d{4}', r'\d{1,2}\.\d{1,2}\.\d{4}',
                r'\d{1,2}:\d{2}', r'вчера', r'сегодня',
                r'\d+\s+минут', r'\d+\s+час',
            ]

            for pattern in date_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    date_str = match.group()
                    break

            # Ищем ссылку
            link = source_url
            try:
                links = post_element.find_elements(By.TAG_NAME, "a")
                for link_element in links:
                    href = link_element.get_attribute("href")
                    if href and href.startswith('http'):
                        link = href
                        break
            except:
                pass

            return {
                'text': text,
                'date': date_str,
                'url': link,
                'source': source_url
            }

        except Exception as e:
            return None

    def search_posts_with_keyword(self, url, keyword, count=5):
        """Поиск постов с определенным ключевым словом"""
        print(f"Ищем посты с ключевым словом: '{keyword}'")
        posts = self.get_posts_data(url)

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

    def parse_multiple_sites(self, urls: List[str], posts_per_site: int = 3) -> Dict[str, List[Dict]]:
        """Парсит несколько сайтов и возвращает результаты"""
        results = {}

        for url in urls:
            try:
                print(f"\n🔍 Начинаем парсинг: {url}")
                posts = self.get_posts_data(url, posts_per_site)
                results[url] = posts
                print(f"✅ Сайт {url}: {len(posts)} постов с ключевыми словами")
            except Exception as e:
                print(f"❌ Ошибка при парсинге {url}: {e}")
                results[url] = []

        return results

    def close(self):
        """Закрытие драйвера"""
        if self.driver:
            self.driver.quit()
            print("✅ Веб-парсер закрыт")


# Функции для использования в Flask
def parse_news_sites():
    """Основная функция для парсинга новостных сайтов"""
    parser = WebParserSelenium()
    try:
        sites = [
            "https://www.nnov.kp.ru/online/",
            "https://nn.aif.ru/",
            "https://dzen.ru/news/region/nizhny_novgorod",
            "https://www.mk.ru/",
            "https://ria.ru/",
            "https://www.rbc.ru/",
            "https://www.kommersant.ru/",
            "https://lenta.ru/",
            "https://news.mail.ru/",
            "https://news.yandex.ru/region/nizhny_novgorod"
        ]

        results = parser.parse_multiple_sites(sites, posts_per_site=3)

        # Статистика
        total_posts = 0
        for url, posts in results.items():
            print(f"📊 {url}: {len(posts)} постов с ключевыми словами")
            total_posts += len(posts)

        print(f"\n🎯 Всего сохранено постов с ключевыми словами: {total_posts}")
        return results

    except Exception as e:
        print(f"❌ Ошибка в основном процессе парсинга: {e}")
        return {}
    finally:
        parser.close()


if __name__ == "__main__":
    # Тестирование
    print("🚀 Запуск тестирования веб-парсера...")
    print("🔍 Ключевые слова: ТНС Энерго, тнс, энерго, электричество")
    results = parse_news_sites()

    # Вывод результатов
    for url, posts in results.items():
        print(f"\n🌐 {url}:")
        for i, post in enumerate(posts, 1):
            print(f"  {i}. {post.get('text', '')[:100]}...")