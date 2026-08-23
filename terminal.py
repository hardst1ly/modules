# terminal.py
from .. import loader, utils
import subprocess
import asyncio
import shlex

@loader.tds  # <-- заменили @loader.module на @loader.tds
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

    @loader.owner
    @loader.command()  # <-- добавили круглые скобки
    async def t(self, message):
        """Выполнить команду в терминале. .t <команда>"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("no_cmd"))
            return
        
        status_msg = await utils.answer(message, self.strings("executing"))
        
        try:
            start = asyncio.get_event_loop().time()
            cmd_list = shlex.split(args)
            proc = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            except asyncio.TimeoutError:
                proc.kill()
                await status_msg.edit_text(self.strings("timeout"))
                return
            
            elapsed = asyncio.get_event_loop().time() - start
            output = stdout.decode('utf-8', errors='replace').strip()
            error = stderr.decode('utf-8', errors='replace').strip()
            
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
            
            if len(result) > 3900:
                result = result[:3900] + "\n... (обрезано)"
            
            result += f"\n\n⏱️ {self.strings('done').format(elapsed)}"
            
            await status_msg.edit_text(f"```bash\n{result}\n```", parse_mode="Markdown")
            
        except FileNotFoundError:
            await status_msg.edit_text(self.strings("error").format("Команда не найдена"))
        except Exception as e:
            await status_msg.edit_text(self.strings("error").format(str(e)))
