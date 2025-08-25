from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
import os


class Base(DeclarativeBase):
	pass


db = SQLAlchemy(model_class=Base)


def create_app():
	app = Flask(__name__)

	# Конфигурация PostgreSQL
	app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/news_db')
	app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
		'pool_size': 10,
		'max_overflow': 20,
		'pool_timeout': 30,
		'pool_recycle': 1800,
	}
	app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

	# Инициализация расширений
	db.init_app(app)

	with app.app_context():
		# Импорт моделей и создание таблиц
		from app import models  # Правильный импорт
		db.create_all()

	# Регистрация blueprints (убедитесь, что routes существует)
	from app.routes import main_bp  # Правильный импорт
	app.register_blueprint(main_bp)

	return app