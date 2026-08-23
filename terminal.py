# meta developer: @hardst1ly

import asyncio
import html
import shlex

from .. import loader, utils


@loader.tds
class TerminalMod(loader.Module):
    """Owner-only local terminal. Ubuntu WSL is the default target."""

    strings = {
        "name": "Terminal",
        "help": (
            "💻 <b>Terminal</b>\n\n"
            "<code>.t команда</code> — Ubuntu WSL (по умолчанию)\n"
            "<code>.t ubuntu команда</code> — Ubuntu WSL\n"
            "<code>.t debian команда</code> — Debian WSL\n"
            "<code>.t win команда</code> — Windows CMD\n"
            "<code>.t status</code> — состояние WSL\n\n"
            "⏱ Таймаут: 120 секунд.\n"
            "📦 Вывод ограничен 12 000 символами."
        ),
        "usage": "❌ Использование: <code>.t [ubuntu|debian|win] команда</code>",
        "running": "⏳ Выполняю...",
        "empty": "❌ Команда пустая.",
        "timeout": "⏱ Команда превысила таймаут <b>120 сек.</b>",
        "error": "❌ Ошибка запуска: <code>{}</code>",
    }

    TIMEOUT = 120
    MAX_OUTPUT = 12000

    async def _run_shell(self, command):
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                output, _ = await asyncio.wait_for(
                    process.communicate(), timeout=self.TIMEOUT
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return None, "timeout"
            return process.returncode, output.decode("utf-8", errors="replace")
        except Exception as e:
            return None, str(e)

    async def _run_wsl(self, distro, command):
        wrapped = "wsl.exe -d {} -- bash -lc {}".format(
            shlex.quote(distro), shlex.quote(command)
        )
        return await self._run_shell(wrapped)

    def _format(self, target, command, code, output):
        output = output or "(нет вывода)"
        if len(output) > self.MAX_OUTPUT:
            output = output[:self.MAX_OUTPUT] + "\n\n...[вывод обрезан]"
        status = "OK" if code == 0 else "exit {}".format(code)
        return (
            "💻 <b>{}</b> <code>{}</code>\n"
            "<code>{}</code>\n\n<pre>{}</pre>"
        ).format(
            html.escape(target),
            html.escape(status),
            html.escape(command),
            html.escape(output),
        )

    @loader.owner
    @loader.command()
    async def t(self, message):
        """[ubuntu|debian|win] команда — терминал; без цели запускает Ubuntu."""
        args = utils.get_args_raw(message).strip()
        if not args:
            await utils.answer(message, self.strings("help"))
            return

        parts = args.split(maxsplit=1)
        first = parts[0].lower()
        explicit_target = first in {"ubuntu", "debian", "win", "windows", "status", "help", "h", "?"}

        if first in {"help", "h", "?"}:
            await utils.answer(message, self.strings("help"))
            return

        if first == "status":
            msg = await utils.answer(message, self.strings("running"))
            code, output = await self._run_shell("wsl.exe -l -v")
            if output == "timeout":
                await utils.answer(msg, self.strings("timeout"))
                return
            if code is None:
                await utils.answer(msg, self.strings("error").format(html.escape(output)))
                return
            await utils.answer(msg, self._format("WSL", "wsl.exe -l -v", code, output))
            return

        if explicit_target:
            target = first
            command = parts[1].strip() if len(parts) > 1 else ""
        else:
            target = "ubuntu"
            command = args

        if not command:
            await utils.answer(message, self.strings("empty"))
            return

        if target in {"win", "windows"}:
            actual = "cmd.exe /d /s /c {}".format(shlex.quote(command))
            display = "Windows"
            msg = await utils.answer(message, self.strings("running"))
            code, output = await self._run_shell(actual)
        elif target in {"ubuntu", "debian"}:
            distro = "Ubuntu" if target == "ubuntu" else "Debian"
            display = distro + " WSL"
            msg = await utils.answer(message, self.strings("running"))
            code, output = await self._run_wsl(distro, command)
        else:
            await utils.answer(message, self.strings("usage"))
            return

        if output == "timeout":
            await utils.answer(msg, self.strings("timeout"))
            return
        if code is None:
            await utils.answer(msg, self.strings("error").format(html.escape(output)))
            return
        await utils.answer(msg, self._format(display, command, code, output))
