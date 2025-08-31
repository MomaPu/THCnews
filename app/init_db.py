from app import create_app
from app.database import db
from app.models.models import NewsSource, NewsPost, PostComment
from sqlalchemy import inspect


def init_db():
	app = create_app()
	with app.app_context():
		try:
			db.create_all()
			print("✅ Таблицы успешно созданы!")

			inspector = inspect(db.engine)
			tables = inspector.get_table_names()
			print("📊 Созданные таблицы:", tables)

		except Exception as e:
			print(f"❌ Ошибка при создании таблиц: {e}")
			import traceback
			traceback.print_exc()


if __name__ == '__main__':
	init_db()