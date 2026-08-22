import aiohttp
import xml.etree.ElementTree as ET
from herokutl.tl.types import Message
from .. import loader, utils

@loader.tds
class PastebinMod(loader.Module):
    """Менеджер Pastebin: загрузка, список и удаление паст"""

    strings = {
        "name": "Pastebin",
        "no_creds": "❌ Сначала настрой доступ: .pb config <dev_key> <логин> <пароль>",
        "created": "✅ Паста создана: {}",
        "deleted": "✅ Паста успешно удалена",
        "error": "❌ Ошибка API: {}",
        "list_empty": "📭 Список паст пуст",
        "list_header": "📋 Твои последние пасты:\n",
        "saved": "✅ Настройки Pastebin сохранены. Сессионный ключ получен.",
        "help": (
            "📋 <b>Pastebin Manager</b>\n"
            "Использование: <code>.pb &lt;действие&gt; [аргументы]</code>\n"
            "(также работает алиас <code>.pastebin</code>)\n\n"
            "🔹 <code>.pb help</code> — Показать это сообщение\n"
            "🔹 <code>.pb config &lt;key&gt; &lt;логин&gt; &lt;пароль&gt;</code> — Настроить доступ\n"
            "🔹 <code>.pb upload &lt;заголовок&gt; [текст]</code> — Создать пасту\n"
            "   (или ответь командой на сообщение/файл)\n"
            "🔹 <code>.pb list</code> — Показать последние 10 паст\n"
            "🔹 <code>.pb delete &lt;ключ&gt;</code> — Удалить пасту по ключу"
        )
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("dev_key", "", "Pastebin API Developer Key", validator=loader.validators.String()),
            loader.ConfigValue("username", "", "Pastebin Username", validator=loader.validators.String()),
            loader.ConfigValue("password", "", "Pastebin Password", validator=loader.validators.String()),
        )
        self._user_key = None
        self.login_url = "https://pastebin.com/api/api_login.php"
        self.post_url = "https://pastebin.com/api/api_post.php"

    async def _get_user_key(self):
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

    @loader.command(alias=["pastebin"])
    async def pb(self, message: Message):
        args = utils.get_args_raw(message).split()
        if not args:
            await utils.answer(message, self.strings["help"])
            return
        
        action = args[0].lower()
        
        if action in ["help", "h"]:
            await utils.answer(message, self.strings["help"])
        elif action in ["config", "c", "set"]:
            if len(args) < 4:
                await utils.answer(message, "❌ Использование: .pb config <dev_key> <логин> <пароль>")
                return
            self.config["dev_key"] = args[1]
            self.config["username"] = args[2]
            self.config["password"] = args[3]
            self._user_key = None
            await utils.answer(message, self.strings["saved"])
        elif action in ["upload", "u", "up"]:
            await self._upload(message, args[1:])
        elif action in ["list", "l"]:
            await self._list(message)
        elif action in ["delete", "del", "d"]:
            await self._delete(message, args[1:])
        else:
            await utils.answer(message, f"❌ Неизвестное действие: {action}\n\n" + self.strings["help"])

    async def _upload(self, message: Message, args):
        user_key = await self._get_user_key()
        if not user_key:
            await utils.answer(message, self.strings["no_creds"])
            return

        title = "Untitled"
        text = ""
        
        if message.is_reply:
            reply = await message.get_reply_message()
            text = reply.text or reply.raw_text or ""
            title = args[0] if args else (reply.file.name if reply.file else "Replied Paste")
            
            # Если ответили на файл (документ), читаем его содержимое
            if reply.document and not text:
                await utils.answer(message, "⏳ Читаю файл...")
                file_bytes = await reply.download_media(bytes)
                if len(file_bytes) > 512000:
                    await utils.answer(message, "❌ Файл слишком большой для Pastebin (макс. 512 КБ)")
                    return
                text = file_bytes.decode('utf-8', errors='ignore')
        else:
            if not args:
                await utils.answer(message, "❌ Использование: .pb upload <заголовок> <текст>\nИли ответь на сообщение/файл: .pb upload <заголовок>")
                return
            title = args[0]
            text = " ".join(args[1:])
        
        if not text:
            await utils.answer(message, "❌ Нет текста или содержимого файла для загрузки")
            return

        data = {
            'api_dev_key': self.config["dev_key"],
            'api_user_key': user_key,
            'api_option': 'paste',
            'api_paste_code': text,
            'api_paste_name': title,
            'api_paste_private': '1',
            'api_paste_format': 'text'
        }
        
        await utils.answer(message, "⏳ Загрузка...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.post_url, data=data) as resp:
                    res_text = await resp.text()
                    if res_text.startswith("Bad API request"):
                        await utils.answer(message, self.strings["error"].format(res_text))
                    else:
                        await utils.answer(message, self.strings["created"].format(res_text))
        except Exception as e:
            await utils.answer(message, self.strings["error"].format(str(e)))

    async def _list(self, message: Message):
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
        user_key = await self._get_user_key()
        if not user_key:
            await utils.answer(message, self.strings["no_creds"])
            return

        if not args:
            await utils.answer(message, "❌ Укажи ключ пасты для удаления: .pb delete <ключ>")
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