from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.database import db


class NewsSource(db.Model):
	__tablename__ = 'news_source'

	id = db.Column(db.Integer, primary_key=True)
	platform = db.Column(db.String(20), nullable=True)
	source_id = db.Column(db.String(100), nullable=False)
	source_name = db.Column(db.String(200))
	source_url = db.Column(db.String(500))
	source_type = db.Column(db.String(50))

	posts = db.relationship("NewsPost", back_populates="source", cascade="all, delete-orphan")

	__table_args__ = (
		Index('ix_news_sources_platform_source_id', 'platform', 'source_id', unique=True),
		Index('ix_news_sources_platform', 'platform'),
	)


class NewsPost(db.Model):
	__tablename__ = 'news_post'

	id = db.Column(db.Integer, primary_key=True)
	platform = db.Column(db.String(20), nullable=True)
	platform_post_id = db.Column(db.String(100), nullable=False)
	source_id = db.Column(db.Integer, db.ForeignKey('news_source.id'), nullable=False)

	title = db.Column(db.String(500))
	text = db.Column(db.Text)
	url = db.Column(db.String(500))

	author = db.Column(db.String(200))
	publish_date = db.Column(db.DateTime)

	likes_count = db.Column(db.Integer, default=0)
	comments_count = db.Column(db.Integer, default=0)
	reposts_count = db.Column(db.Integer, default=0)
	views_count = db.Column(db.Integer, default=0)

	keywords = db.Column(ARRAY(db.String(50)))
	platform_data = db.Column(JSONB)

	source = db.relationship("NewsSource", back_populates="posts")
	comments = db.relationship("PostComment", back_populates="post", cascade="all, delete-orphan")

	__table_args__ = (
		Index('ix_news_posts_platform_post_id', 'platform', 'platform_post_id', unique=True),
		Index('ix_news_posts_publish_date', 'publish_date'),
		Index('ix_news_posts_source_id', 'source_id'),
		Index('ix_news_posts_keywords', 'keywords', postgresql_using='gin'),
	)


class PostComment(db.Model):
	__tablename__ = 'post_comment'

	id = db.Column(db.Integer, primary_key=True)
	post_id = db.Column(db.Integer, db.ForeignKey('news_post.id'), nullable=False)
	platform_comment_id = db.Column(db.String(100), nullable=False)
	platform_user_id = db.Column(db.String(100))

	text = db.Column(db.Text)
	original_text = db.Column(db.Text)
	sentiment = db.Column(db.String(30))
	publish_date = db.Column(db.DateTime)

	likes_count = db.Column(db.Integer, default=0)
	platform_data = db.Column(JSONB)

	post = db.relationship("NewsPost", back_populates="comments")

	__table_args__ = (
		Index('ix_post_comments_post_id', 'post_id'),
		Index('ix_post_comments_sentiment', 'sentiment'),
		Index('ix_post_comments_platform_id', 'platform_comment_id'),
		Index('ix_post_comments_platform_user', 'platform_user_id'),
	)