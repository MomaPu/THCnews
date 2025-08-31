import asyncio
import sys
import os
from datetime import datetime

# Добавляем корневую директорию в Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.append(root_dir)

# Создаем Flask приложение перед импортом других модулей
from app import create_app


# Создаем приложение
app = create_app()


async def parse_telegram_channels():
	"""Запускает парсинг Telegram каналов"""
	try:
		from app.services.telegram_service import TelegramService

		service = TelegramService()
		results = await service.get_news(
			channels=['Dzerzhinsk_blackhole', 'tns_energo_nn'],
			keywords=['ТНС энерго НН', 'ТНС энерго Нижний Новгород', 'ТНС',
					  'Энергосбыт Нижний Новгород', "ТНС Нижний"
		],
			days=5
		)

		return {'saved': len(results), 'details': results}

	except Exception as e:
		print(f"❌ Ошибка Telegram парсера: {e}")
		return {'saved': 0, 'error': str(e)}


async def parse_vk_groups():
	"""Запускает парсинг VK групп"""
	try:
		from app.services.vk_service import VKService

		# Замените на ваш реальный VK токен
		vk_service = VKService(token='5746854757468547574685473b547eebd055746574685473fdcc76d76189e0967f0739b')

		results = await vk_service.parse_groups_sequentially()

		total_posts = 0
		for group_result in results.values():
			total_posts += len(group_result.get('posts', []))

		return {'saved': total_posts, 'details': results}

	except Exception as e:
		print(f"❌ Ошибка VK парсера: {e}")
		return {'saved': 0, 'error': str(e)}


def parse_odnoklassniki():
	"""Запускает парсинг Одноклассников"""
	try:
		from app.services.browser_parser import BrowserParser

		parser = BrowserParser()
		results = parser.parse_odnoklassniki_groups()

		return {'saved': results.get('saved', 0), 'details': results}

	except Exception as e:
		print(f"❌ Ошибка Одноклассники парсера: {e}")
		return {'saved': 0, 'error': str(e)}


def parse_web_sites():
	"""Запускает парсинг новостных сайтов"""
	try:
		from app.services.browser_parser import parse_news_sites

		print("\n🌐 ЗАПУСК ВЕБ-ПАРСЕРА (НОВОСТНЫЕ САЙТЫ)")
		print("-" * 50)

		results = parse_news_sites()

		total_posts = 0
		for url, posts in results.items():
			total_posts += len(posts)

		return {'saved': total_posts, 'details': results}

	except Exception as e:
		print(f"❌ Ошибка веб-парсера: {e}")
		return {'saved': 0, 'error': str(e)}


async def run_parsers_async():
	"""Асинхронно запускает все парсеры"""
	print("🚀 Запуск всех парсеров последовательно...")
	print("🚀 ЗАПУСК ВСЕХ ПАРСЕРОВ")
	print("=" * 60)

	# Запускаем в контексте приложения
	with app.app_context():
		try:
			print("\n📱 ЗАПУСК TELEGRAM ПАРСЕРА")
			print("-" * 40)
			telegram_results = await parse_telegram_channels()
			print(f"✅ Telegram: сохранено {telegram_results['saved']} постов")

			print("\n🔵 ЗАПУСК VK ПАРСЕРА")
			print("-" * 40)
			vk_results = await parse_vk_groups()
			print(f"✅ VK: сохранено {vk_results['saved']} постов")

			print("\n🟠 ЗАПУСК ODNOKLASSNIKI ПАРСЕРА")
			print("-" * 40)
			ok_results = parse_odnoklassniki()
			print(f"✅ Одноклассники: сохранено {ok_results['saved']} постов")

			print("\n🌐 ЗАПУСК ВЕБ-ПАРСЕРА (НОВОСТНЫЕ САЙТЫ)")
			print("-" * 50)
			web_results = parse_web_sites()
			print(f"✅ Веб-сайты: сохранено {web_results['saved']} постов")

			# Сводка
			print("\n" + "=" * 60)
			print("📊 СВОДКА РЕЗУЛЬТАТОВ:")
			print(f"📱 Telegram: {telegram_results['saved']} постов")
			print(f"🔵 VK: {vk_results['saved']} постов")
			print(f"🟠 Одноклассники: {ok_results['saved']} постов")
			print(f"🌐 Веб-сайты: {web_results['saved']} постов")
			total = (telegram_results['saved'] + vk_results['saved'] +
					 ok_results['saved'] + web_results['saved'])
			print(f"📈 Всего: {total} постов")
			print("=" * 60)

			return {
				'telegram': telegram_results,
				'vk': vk_results,
				'odnoklassniki': ok_results,
				'web': web_results,
				'total': total
			}

		except Exception as e:
			print(f"❌ Критическая ошибка при запуске парсеров: {e}")
			import traceback
			traceback.print_exc()
			return {'error': str(e)}


def run_parsers():
	"""Синхронная обертка для запуска парсеров"""
	return asyncio.run(run_parsers_async())


if __name__ == "__main__":
	run_parsers()