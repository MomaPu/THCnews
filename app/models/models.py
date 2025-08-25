from datetime import datetime
from app.config import db
from sqlalchemy import Index, text
from sqlalchemy.dialects.postgresql import ARRAY

class NewsSource(db.Model):
	__tablename__ = 'news_source'

	id = db.Column(db.Integer, primary_key=True)
	platform = db.Column(db.String(20),nullable=True)
	source_id = db.Column(db.String(100), nullable=False)

	posts = db.relationship("NewsPost",black_populates="source",cascade="all, delete-orphan")

	__table_args__ = (
		Index('ix_news_sources_platform_source_id', 'platform', 'source_id', unique=True),
		Index('ix_news_sources_platform', 'platform'),
	)


class NewsPost(db.Model):
	__tablename__ = 'news_post'

	id = db.Column(db.Integer, primary_key=True)
	platform = db.Column(db.String(20), nullable=True)
	source_id = db.Column(db.Integer, db.ForeignKey('news_source.id'), nullable=False)

	title = db.Column(db.String(500))
	text = db.Column(db.Text)
	url = db.Column(db.String(500))

	author = db.Column(db.String(200))
	publish_date = db.Column(db.Datetime)

	likes_count = db.Column(db.Integer, default=0)
	comments_count = db.Column(db.Integer,default=0)

	source = db.relationship("NewsSource", back_populates="posts")
	comments = db.relationship("PostComment", back_populates="post", cascade="all, delete-orphan")


	__table_args__ = (
		Index('ix_news_posts_platform_post_id', 'platform', 'platform_post_id', unique=True),
		Index('ix_news_posts_publish_date', 'publish_date'),
		Index('ix_news_posts_source_id', 'source_id'),
		Index('ix_news_posts_keywords', 'keywords', postgresql_using='gin'),
	)

