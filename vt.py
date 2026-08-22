# meta developer: @hardst1ly
# requires: aiohttp

import hashlib
import html
import os
import tempfile

import aiohttp
from .. import loader, utils

VT_SMALL_UPLOAD_LIMIT = 32 * 1024 * 1024
VT_UPLOAD_LIMIT = 650 * 1024 * 1024
VT_CHECK_LIMIT = 1024 * 1024 * 1024


@loader.tds
class VirusTotalMod(loader.Module):
    """VirusTotal checker: hash lookup for files up to 1 GB, upload up to 650 MB."""

    strings = {
        "name": "VirusTotal",
        "no_key": "❌ Сначала укажи API-ключ: <code>.config VirusTotal</code>",
        "no_file": "❌ Ответь командой <code>.vt</code> на файл.",
        "too_big": "❌ Файл больше лимита проверки — <b>1 GB</b>.",
        "upload_big": "❌ Для загрузки VirusTotal принимает максимум <b>650 MB</b>.",
        "checking": "🔎 Считаю SHA-256 и проверяю VirusTotal...",
        "uploading": "📤 Файл не найден в базе. Загружаю его в VirusTotal...",
        "not_found": "ℹ️ В базе VirusTotal файла пока нет.\n\n📄 <code>{}</code>\n📦 <b>{}</b>\n🧬 <code>{}</code>\n\nЕсли хочешь отправить его на анализ: <code>.vt upload</code>",
        "uploaded": "✅ Файл отправлен в VirusTotal.\n\n📄 <code>{}</code>\n📦 <b>{}</b>\n🧬 <code>{}</code>\n\n🆔 Analysis ID: <code>{}</code>",
        "error": "❌ VirusTotal: <code>{}</code>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("api_key", "", "VirusTotal API key")
        )

    def _size(self, n):
        if n >= 1024 * 1024 * 1024:
            return f"{n / 1024 / 1024 / 1024:.2f} GB"
        return f"{n / 1024 / 1024:.2f} MB"

    def _sha256(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(4 * 1024 * 1024):
                h.update(chunk)
        return h.hexdigest()

    async def _get(self, url):
        headers = {"x-apikey": self.config["api_key"]}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.get(url, headers=headers) as r:
                text = await r.text()
                if r.status == 404:
                    return None
                if r.status >= 400:
                    raise RuntimeError(f"HTTP {r.status}: {text[:300]}")
                return await r.json()

    async def _large_upload_url(self):
        data = await self._get("https://www.virustotal.com/api/v3/files/upload_url")
        if not data or not data.get("data"):
            raise RuntimeError("VirusTotal не вернул upload URL")
        return data["data"]

    async def _upload(self, path, filename, size):
        url = "https://www.virustotal.com/api/v3/files"
        if size > VT_SMALL_UPLOAD_LIMIT:
            url = await self._large_upload_url()

        headers = {"x-apikey": self.config["api_key"]}
        timeout = aiohttp.ClientTimeout(total=1800)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            with open(path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("file", f, filename=filename, content_type="application/octet-stream")
                async with s.post(url, headers=headers, data=form) as r:
                    text = await r.text()
                    if r.status >= 400:
                        raise RuntimeError(f"HTTP {r.status}: {text[:500]}")
                    data = await r.json()
                    return data.get("data", {}).get("id", "unknown")

    async def vtcmd(self, message):
        """[upload] — проверить файл через VirusTotal. Проверка до 1 GB."""
        api_key = str(self.config["api_key"]).strip()
        if not api_key:
            await utils.answer(message, self.strings("no_key"))
            return

        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_file"))
            return

        upload = "upload" in utils.get_args_raw(message).lower().split()
        size = getattr(getattr(reply, "file", None), "size", 0) or 0
        if size > VT_CHECK_LIMIT:
            await utils.answer(message, self.strings("too_big"))
            return
        if upload and size > VT_UPLOAD_LIMIT:
            await utils.answer(message, self.strings("upload_big"))
            return

        path = None
        try:
            msg = await utils.answer(message, self.strings("checking"))
            path = await reply.download_media(file=tempfile.mktemp(prefix="vt_"))
            real_size = os.path.getsize(path)
            if real_size > VT_CHECK_LIMIT:
                await utils.answer(msg, self.strings("too_big"))
                return

            sha = self._sha256(path)
            report = await self._get(f"https://www.virustotal.com/api/v3/files/{sha}")

            if report:
                a = report.get("data", {}).get("attributes", {})
                st = a.get("last_analysis_stats", {}) or {}
                malicious = int(st.get("malicious", 0) or 0)
                suspicious = int(st.get("suspicious", 0) or 0)
                verdict = "🔴 Есть детекты" if malicious else ("🟠 Подозрительно" if suspicious else "🟢 Чисто")
                link = f"https://www.virustotal.com/gui/file/{sha}"
                await utils.answer(msg, (
                    f"<b>{verdict}</b>\n\n"
                    f"📄 <code>{html.escape(getattr(getattr(reply, 'file', None), 'name', None) or 'file')}</code>\n"
                    f"📦 <b>{self._size(real_size)}</b>\n"
                    f"🧬 <code>{sha}</code>\n\n"
                    f"📊 Malicious: <b>{malicious}</b>\n"
                    f"📊 Suspicious: <b>{suspicious}</b>\n\n"
                    f"🔗 <a href=\"{link}\">VirusTotal</a>"
                ))
                return

            if not upload:
                await utils.answer(msg, self.strings("not_found").format(
                    html.escape(getattr(getattr(reply, "file", None), "name", None) or "file"),
                    self._size(real_size), sha))
                return

            if real_size > VT_UPLOAD_LIMIT:
                await utils.answer(msg, self.strings("upload_big"))
                return

            await utils.answer(msg, self.strings("uploading"))
            analysis_id = await self._upload(path, getattr(getattr(reply, "file", None), "name", None) or "file", real_size)
            await utils.answer(msg, self.strings("uploaded").format(
                html.escape(getattr(getattr(reply, "file", None), "name", None) or "file"),
                self._size(real_size), sha, html.escape(str(analysis_id))))
        except Exception as e:
            await utils.answer(message, self.strings("error").format(html.escape(str(e))))
        finally:
            if path:
                try:
                    os.remove(path)
                except Exception:
                    pass
