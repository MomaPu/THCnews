# telegram_service.py
import asyncio
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 20304623
API_HASH = 'c1622024c0ad17c26fbd6b34f1d9ef1c'

class TelegramService:
    def __init__(self, session_string=None, file_session_name='user_session'):
        self.session_string = session_string
        if session_string:
            self.client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        else:
            # Файловая сессия (будет храниться в user_session.session)
            self.client = TelegramClient(file_session_name, API_ID, API_HASH)

    async def start_client(self):
        try:
            # .start() безопасно — если session_string валидна, не будет запроса телефона
            await self.client.start()
            me = await self.client.get_me()
            print(f"✅ Успешный вход: {me.first_name} (@{getattr(me, 'username', None)})")
            # Если мы стартовали из файловой сессии и хотим строку — можно её сгенерировать:
            if not self.session_string:
                try:
                    new_session_string = self.client.session.save()
                    # Если нужно, можно обернуть в StringSession, но save() у текущей сессии уже возвращает строку
                    print("🆕 Сгенерированная строка сессии (скопируйте для будущих запусков):")
                    print(new_session_string)
                    self.session_string = new_session_string
                except Exception:
                    # не критично — просто уведомим
                    print("⚠️ Не удалось сгенерировать StringSession автоматически.")
            return True
        except Exception as e:
            print(f"❌ Ошибка авторизации: {e}")
            return False

    # ... остальной код без изменений (get_news, _get_comments, close) ...
    async def get_news(self, channels, keywords, days=3):
        success = await self.start_client()
        if not success:
            print("🚫 Не удалось авторизоваться")
            return []

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        results = []
        for channel in channels:
            try:
                print(f"📡 Подключаюсь к {channel}...")
                entity = await self.client.get_entity(channel)
                print(f"✅ Найден канал: {getattr(entity, 'title', channel)}")

                async for message in self.client.iter_messages(entity, limit=100):
                    if message.date.replace(tzinfo=timezone.utc) < start_date:
                        break
                    if message.text and any(kw.lower() in message.text.lower() for kw in keywords):
                        comments = await self._get_comments(entity, message.id)
                        results.append({
                            'date': message.date.strftime('%Y-%m-%d %H:%M'),
                            'text': message.text,
                            'url': f"https://t.me/{channel}/{message.id}",
                            'comments': comments
                        })
            except Exception as e:
                print(f"❌ Ошибка в канале {channel}: {e}")
                continue

        return sorted(results, key=lambda x: x['date'], reverse=True)

    async def _get_comments(self, entity, post_id):
        comments = []
        try:
            async for comment in self.client.iter_messages(entity, reply_to=post_id, limit=3):
                if comment and comment.text:
                    comments.append({
                        'date': comment.date.strftime('%H:%M'),
                        'text': comment.text[:200]
                    })
        except Exception as e:
            print(f"💬 Не удалось получить комментарии: {e}")
        return comments

    async def close(self):
        await self.client.disconnect()
        print("🔌 Соединение закрыто")

# Пример использования: подставьте сгенерированную строку
async def main():
    session_str = "1ApWapzMBu0w8dRJ4o4ABFnnckf-WPTDT8ZXaeZ4OHWpxt5HN4FYkgI_2zktBn6xvxyl3KhNTuwHoTH4dA-_eqGCGbglJom-MZPJcqSYTUEQ0oTevSOg-8ksYX2QmowqdL-BYZj6S2oQTwksLh8HaArfn0a01X0NZh0AUE-Ymwr_sMd7TxkIgKiDAceEBWJarMmwqVL--MkokTjebyWxBlr3hSNFmOEJfgB5j_y5VahDPt2SWqIZcn9TSrmybf_goABgSbnxReGLQrJQUe4iXNkXBRTFgwxU6lpYZJZiNKtW6nO9mvxnv_5_b-zYZwS0AXhtv6J-57c55DER_so2JbRsX3C8-04M="
    service = TelegramService(session_string=None)  # или TelegramService(session_string=session_str)
    try:
        news = await service.get_news(
            channels=['tns_energo_nn'],
            keywords=['интернет', 'авария', 'проблем', 'связь'],
            days=2
        )
        print(f"\n📊 ИТОГ: Найдено {len(news)} сообщений:")
    finally:
        await service.close()

if __name__ == '__main__':
    asyncio.run(main())
