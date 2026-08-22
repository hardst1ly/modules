import aiohttp
import xml.etree.ElementTree as ET
from herokutl.tl.types import Message
from .. import loader, utils

@loader.tds
class PastebinMod(loader.Module):
    """Менеджер Pastebin: загрузка (add), список (list) и удаление (delete)"""

    strings = {
        "name": "Pastebin",
        "no_creds": "❌ Настрой доступ через .config Pastebin (dev_key, username, password)",
        "no_reply": "❌ Ответь на сообщение или файл, который хочешь залить",
        "created": "✅ Pastebin создан!\n\n🔗 Обычная: {}\n📄 Raw: {}",
        "deleted": "✅ Pastebin успешно удалён",
        "error": "❌ Ошибка API: {}",
        "list_empty": "📭 Список Pastebin пуст",
        "list_header": "📋 Твои последние Pastebin:\n",
        "help": (
            "<b>📋 Pastebin Manager</b>\n\n"
            "🔹 <code>.pb add [заголовок]</code> — ответь на сообщение или файл\n"
            "🔹 <code>.pb list</code> — показать последние 10 Pastebin\n"
            "🔹 <code>.pb delete &lt;ключ&gt;</code> — удалить Pastebin по ключу\n\n"
            "⚙️ Настройка API: <code>.config Pastebin</code>"
        )
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "dev_key", "",
                lambda: "Pastebin API Developer Key (брать в настройках аккаунта Pastebin)",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "username", "",
                lambda: "Логин от Pastebin",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "password", "",
                lambda: "Пароль от Pastebin (для генерации сессионного ключа)",
                validator=loader.validators.Hidden(loader.validators.String()),
            ),
        )
        self._user_key = None
        self.login_url = "https://pastebin.com/api/api_login.php"
        self.post_url = "https://pastebin.com/api/api_post.php"

    async def _get_user_key(self):
        """Автоматически получает и кэширует сессионный ключ из логина/пароля"""
        if self._user_key:
            return self._user_key
        
        if not self.config["dev_key"] or not self.config["username"] or not self.config["password"]:
            return None

        data = {
            'api_dev_key': self.config["dev_key"],
            'api_user_name': self.config["username"],
            'api_user_password': self.config["password"]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.login_url, data=data) as resp:
                    text = await resp.text()
                    if text.startswith("Bad API request"):
                        return None
                    self._user_key = text
                    return self._user_key
        except Exception:
            return None

    @loader.command()
    async def pb(self, message: Message):
        """- управление pastebin"""
        args = utils.get_args_raw(message).split()
        
        if not args:
            await utils.answer(message, self.strings["help"])
            return
        
        action = args[0].lower()
        
        if action in ["help", "h"]:
            await utils.answer(message, self.strings["help"])
        elif action in ["add", "a", "up", "upload"]:
            await self._add(message, args[1:])
        elif action in ["list", "l"]:
            await self._list(message)
        elif action in ["delete", "del", "d"]:
            await self._delete(message, args[1:])
        else:
            await utils.answer(message, f"❌ Неизвестное действие: {action}\n\n" + self.strings["help"])

    async def _add(self, message: Message, args):
        """Загрузка сообщения/файла на pastebin"""
        user_key = await self._get_user_key()
        if not user_key:
            await utils.answer(message, self.strings["no_creds"])
            return

        if not message.is_reply:
            await utils.answer(message, self.strings["no_reply"])
            return

        reply = await message.get_reply_message()
        title = args[0] if args else "Paste"
        text = ""
        
        # Читаем текст из сообщения
        if reply.text or reply.raw_text:
            text = reply.text or reply.raw_text
            if not args:
                title = reply.file.name if reply.file else "Paste"
                
        # Если это документ (файл), читаем его содержимое
        elif reply.document:
            if not args and reply.file and reply.file.name:
                title = reply.file.name
                
            await utils.answer(message, "⏳ Читаю файл...")
            file_bytes = await reply.download_media(bytes)
            
            if len(file_bytes) > 512000:
                await utils.answer(message, "❌ Файл слишком большой для Pastebin (макс. 512 КБ)")
                return
            
            text = file_bytes.decode('utf-8', errors='ignore')
        else:
            await utils.answer(message, "❌ В сообщении нет текста или файла для загрузки")
            return

        if not text:
            await utils.answer(message, "❌ Пустое содержимое")
            return

        data = {
            'api_dev_key': self.config["dev_key"],
            'api_user_key': user_key,
            'api_option': 'paste',
            'api_paste_code': text,
            'api_paste_name': title,
            'api_paste_private': '1',  # 1 = unlisted (доступ по ссылке)
            'api_paste_format': 'text'
        }
        
        await utils.answer(message, "⏳ Загрузка на Pastebin...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.post_url, data=data) as resp:
                    res_text = await resp.text()
                    if res_text.startswith("Bad API request"):
                        await utils.answer(message, self.strings["error"].format(res_text))
                    else:
                        # Извлекаем ключ пасты из URL
                        paste_key = res_text.split('/')[-1].strip()
                        
                        # Формируем обе ссылки
                        normal_link = f"https://pastebin.com/{paste_key}"
                        raw_link = f"https://pastebin.com/raw/{paste_key}"
                        
                        await utils.answer(message, self.strings["created"].format(normal_link, raw_link))
        except Exception as e:
            await utils.answer(message, self.strings["error"].format(str(e)))

    async def _list(self, message: Message):
        """Показывает список твоих Pastebin"""
        user_key = await self._get_user_key()
        if not user_key:
            await utils.answer(message, self.strings["no_creds"])
            return

        data = {
            'api_dev_key': self.config["dev_key"],
            'api_user_key': user_key,
            'api_option': 'list',
            'api_results_limit': 10
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.post_url, data=data) as resp:
                    text = await resp.text()
                    if text.startswith("Bad API request"):
                        await utils.answer(message, self.strings["error"].format(text))
                        return
                    
                    root = ET.fromstring(text)
                    pastes = []
                    for paste in root.findall('paste'):
                        key = paste.find('paste_key').text
                        title = paste.find('paste_title').text or "Untitled"
                        url = paste.find('paste_url').text
                        pastes.append(f"• <a href='{url}'>{title}</a> <code>{key}</code>")
                    
                    if not pastes:
                        await utils.answer(message, self.strings["list_empty"])
                    else:
                        await utils.answer(message, self.strings["list_header"] + "\n".join(pastes))
        except Exception as e:
            await utils.answer(message, self.strings["error"].format(str(e)))

    async def _delete(self, message: Message, args):
        """Удаляет Pastebin по ключу"""
        user_key = await self._get_user_key()
        if not user_key:
            await utils.answer(message, self.strings["no_creds"])
            return

        if not args:
            await utils.answer(message, "❌ Укажи ключ: <code>.pb delete &lt;ключ&gt;</code>")
            return

        key = args[0]
        data = {
            'api_dev_key': self.config["dev_key"],
            'api_user_key': user_key,
            'api_option': 'delete',
            'api_paste_key': key
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.post_url, data=data) as resp:
                    res_text = await resp.text()
                    if res_text.startswith("Bad API request"):
                        await utils.answer(message, self.strings["error"].format(res_text))
                    else:
                        await utils.answer(message, self.strings["deleted"])
        except Exception as e:
            await utils.answer(message, self.strings["error"].format(str(e)))
