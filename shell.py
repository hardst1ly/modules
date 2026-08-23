# shellexec.py — упрощённая версия без дублирования
from .. import loader, utils
import subprocess
import asyncio
import shlex

@loader.module(name="ShellExec")
class ShellExecMod(loader.Module):
    """Выполнение системных команд (только владелец)"""
    
    strings = {
        "name": "ShellExec",
        "no_cmd": "❌ Укажите команду. Пример: .exec ls -la",
        "done": "✅ Выполнено за {:.2f} сек",
        "error": "❌ Ошибка: {}",
        "timeout": "⏰ Команда выполнялась слишком долго и была прервана.",
    }

    @loader.owner
    @loader.command()
    async def exec(self, message):
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("no_cmd"))
            return
        
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
                await utils.answer(message, self.strings("timeout"))
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
            
            await utils.answer(message, f"```bash\n{result}\n```", parse_mode="Markdown")
            
        except FileNotFoundError:
            await utils.answer(message, self.strings("error").format("Команда не найдена"))
        except Exception as e:
            await utils.answer(message, self.strings("error").format(str(e)))
