# terminal.py
from .. import loader, utils
import subprocess
import asyncio
import shlex

@loader.module(
    name="TerminalMod",
    author="YourName",
    version="1.0.0"
)
class TerminalMod(loader.Module):
    """Выполнение команд терминала (только для владельца)"""
    
    strings = {
        "name": "TerminalMod",
        "no_cmd": "❌ Укажите команду. Пример: .t ls -la",
        "executing": "⏳ Выполняю...",
        "done": "✅ Выполнено за {:.2f} сек",
        "error": "❌ Ошибка: {}",
        "timeout": "⏰ Команда выполнялась слишком долго и была прервана.",
        "owner_only": "🚫 Эта команда доступна только владельцу бота."
    }

    @loader.owner  # Только владелец может использовать
    @loader.command
    async def t(self, message):
        """Выполнить команду в терминале. .t <команда>"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("no_cmd"))
            return
        
        # Отправляем сообщение о начале выполнения
        status_msg = await utils.answer(message, self.strings("executing"))
        
        # Запускаем команду с таймаутом (30 сек)
        try:
            start = asyncio.get_event_loop().time()
            # Разбиваем команду на аргументы безопасно
            cmd_list = shlex.split(args)
            # Выполняем в асинхронном режиме
            proc = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            # Ждём завершения с таймаутом 30 секунд
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            except asyncio.TimeoutError:
                proc.kill()
                await status_msg.edit_text(self.strings("timeout"))
                return
            
            elapsed = asyncio.get_event_loop().time() - start
            output = stdout.decode('utf-8', errors='replace').strip()
            error = stderr.decode('utf-8', errors='replace').strip()
            
            # Формируем результат
            result = ""
            if output:
                result += output
            if error:
                if result:
                    result += "\n\n[stderr]\n" + error
                else:
                    result = "[stderr]\n" + error
            
            if not result:
                result = "(пустой вывод)"
            
            # Обрезаем, если слишком длинное (Telegram лимит 4096 символов)
            if len(result) > 3900:
                result = result[:3900] + "\n... (обрезано)"
            
            # Добавляем время выполнения
            result += f"\n\n⏱️ {self.strings('done').format(elapsed)}"
            
            await status_msg.edit_text(f"```bash\n{result}\n```", parse_mode="Markdown")
            
        except FileNotFoundError:
            await status_msg.edit_text(self.strings("error").format("Команда не найдена"))
        except Exception as e:
            await status_msg.edit_text(self.strings("error").format(str(e)))