from .. import loader, utils
import subprocess
import asyncio
import shlex

@loader.module(name="MyTerminal")  # <-- уникальное имя, не системное
class MyTerminalMod(loader.Module):
    strings = {
        "name": "MyTerminal",
        "no_cmd": "❌ Укажите команду.",
        "done": "✅ Выполнено за {:.2f} сек",
        "error": "❌ Ошибка: {}",
        "timeout": "⏰ Команда выполнялась слишком долго.",
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
            cmd = shlex.split(args)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                await utils.answer(message, self.strings("timeout"))
                return
            elapsed = asyncio.get_event_loop().time() - start
            out = stdout.decode('utf-8', errors='replace').strip()
            err = stderr.decode('utf-8', errors='replace').strip()
            result = out
            if err:
                result += "\n\n[stderr]\n" + err
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
