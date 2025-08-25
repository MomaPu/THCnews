from app.services.vk_service import VKService


def main():
	# Инициализация сервиса
	vk_service = VKService(token='5746854757468547574685473b547eebd055746574685473fdcc76d76189e0967f0739b')

	#domain = "nn800"
	#search_keywords = ['нижний','онлайн']
	search_days = 30
	#news = vk_service.get_company_news(domain)
	results = vk_service.get_posts_with_comments(
		group_domain="tns_energo_nn",
		keywords= ['Кассы','интенсивной','важна','вдохновением'],
		comments_count=10
	)
	# Выводим результаты
	'''print(f"\nНайдено {len(news)} постов для {domain}:")
	for i, post in enumerate(news, 1):
		print(f"\nПост #{i}:")
		print(f"Текст: {post['text'][:100]}...")
		print(f"Дата: {post['date']}")
		print(f"URL: {post['url']}")'''
	'''
	# Вывод результатов
	print(f"Найдено {len(results)} постов:")
	for i, post in enumerate(results, 1):
		print(f"\n#{i} [{post['date']}] Лайков: {post['likes']}")
		print(post['text'][:200] + ("..." if len(post['text']) > 200 else ""))
		print(post['url'])
		'''
	for post in results:
		print(f"\nПост: {post['text'][:100]}... ({post['date']})")
		print(f"URL: {post['url']}")
		print(f"Комментариев: {len(post['comments'])}")

		for i, comment in enumerate(post['comments'][:3], 1):  # Первые 3 комментария
			author = comment.get('author', {}).get('name', 'Аноним')
			print(f"  {i}. [{author}]: {comment['text'][:50]}...")

if __name__ == "__main__":
	main()