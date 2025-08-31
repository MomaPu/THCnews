from app.config import create_app, db
from app.models.models import NewsSource, NewsPost
from sqlalchemy import text  # Добавьте этот импорт

app = create_app()

with app.app_context():
	# Проверяем подключение - ИСПРАВЛЕННАЯ ВЕРСИЯ
	try:
		result = db.session.execute(text('SELECT 1'))  # Добавьте text()
		print("✅ Подключение к БД успешно")
	except Exception as e:
		print(f"❌ Ошибка подключения: {e}")
		import traceback

		traceback.print_exc()
		exit(1)

	# Проверяем таблицы
	try:
		tables = db.inspect(db.engine).get_table_names()
		print(f"📊 Таблицы в базе: {tables}")
	except Exception as e:
		print(f"❌ Ошибка при проверке таблиц: {e}")
		exit(1)

	# Создаем тестовые данные
	try:
		if 'news_source' in tables:
			# Проверяем, нет ли уже тестовых данных
			existing = NewsSource.query.filter_by(source_id='test_channel').first()
			if not existing:
				test_source = NewsSource(
					platform='test',
					source_id='test_channel',
					source_name='Test Channel',
					source_type='test'
				)
				db.session.add(test_source)
				db.session.flush()

				test_post = NewsPost(
					platform='test',
					platform_post_id='12345',  # Строковый ID!
					source_id=test_source.id,
					text='Test post content',
					author='Test Author'
				)
				db.session.add(test_post)
				db.session.commit()
				print("✅ Тестовые данные добавлены успешно")
			else:
				print("ℹ️ Тестовые данные уже существуют")

		# Читаем данные обратно
		posts = NewsPost.query.all()
		print(f"📝 Постов в базе: {len(posts)}")
		for post in posts:
			print(f"  - ID: {post.platform_post_id} (тип: {type(post.platform_post_id).__name__})")

	except Exception as e:
		print(f"❌ Ошибка при работе с данными: {e}")
		db.session.rollback()
		import traceback

		traceback.print_exc()