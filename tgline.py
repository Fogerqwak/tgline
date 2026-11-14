#!/usr/bin/env python3
"""tgline: a Telegram client for the terminal. Interactive shell + scriptable commands."""
import argparse
import asyncio
import getpass
import json
import os
import platform
import shlex
import sys
from pathlib import Path

from telethon import TelegramClient, errors, events, utils

__version__ = "0.1.0"

HOME = Path(
    os.environ.get("TGLINE_HOME")
    or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "tgline"
)
CONFIG = HOME / "config.json"
SESSION = HOME / "session"  # Telethon adds .session


class CliError(Exception):
    pass


# ---------- credentials & client ----------

def load_creds(interactive):
    env_id, env_hash = os.environ.get("TG_API_ID"), os.environ.get("TG_API_HASH")
    if env_id and env_hash:
        return int(env_id), env_hash
    if CONFIG.exists():
        c = json.loads(CONFIG.read_text())
        return int(c["api_id"]), c["api_hash"]
    if not interactive:
        raise CliError("no API credentials. Run: tgline login")
    print("tgline needs your own api_id / api_hash.")
    print("Get them at https://my.telegram.org -> API development tools (takes a minute).")
    try:
        api_id = int(input("api_id: ").strip())
    except ValueError:
        raise CliError("api_id must be a number")
    api_hash = input("api_hash: ").strip()
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"api_id": api_id, "api_hash": api_hash}))
    CONFIG.chmod(0o600)
    return api_id, api_hash


def make_client(interactive=False):
    HOME.mkdir(parents=True, exist_ok=True)
    HOME.chmod(0o700)  # session file = full account access
    api_id, api_hash = load_creds(interactive)
    return TelegramClient(
        str(SESSION), api_id, api_hash,
        device_model="tgline", system_version=platform.system(), app_version=__version__,
    )


# ---------- formatting ----------

def media_kind(m):
    if not m.media:
        return None
    if m.photo:
        return "photo"
    if m.voice:
        return "voice"
    if m.video_note:
        return "video note"
    if m.video:
        return "video"
    if m.sticker:
        return "sticker"
    if m.file and m.file.name:
        return f"file {m.file.name}"
    return type(m.media).__name__.removeprefix("MessageMedia").lower()


def as_dict(m, chat=None):
    return {
        "id": m.id,
        "date": m.date.isoformat(),
        "chat_id": m.chat_id,
        "chat": chat,
        "sender_id": m.sender_id,
        "sender": "me" if m.out else (utils.get_display_name(m.sender) if m.sender else None),
        "out": m.out,
        "reply_to": m.reply_to_msg_id,
        "text": m.message or "",
        "media": media_kind(m),
    }


def fmt(m, chat=None):
    d = as_dict(m, chat)
    when = m.date.astimezone().strftime("%Y-%m-%d %H:%M")
    where = f"{chat} | " if chat else ""
    body = d["text"]
    if d["media"]:
        body = f"[{d['media']}] {body}".rstrip()
    reply = f"(re #{d['reply_to']}) " if d["reply_to"] else ""
    return f"[{when}] #{m.id} {where}{d['sender'] or '?'}: {reply}{body}"


def emit(m, as_json, chat=None):
    print(json.dumps(as_dict(m, chat), ensure_ascii=False) if as_json else fmt(m, chat), flush=True)


# ---------- chat lookup ----------

def pick(dialogs, q):
    """Match a chat by id or name. Pure, so it is testable."""
    if q.lstrip("-").isdigit():
        hits = [d for d in dialogs if d.id == int(q)]
    else:
        ql = q.lower()
        hits = [d for d in dialogs if d.name.lower() == ql] or [
            d for d in dialogs if ql in d.name.lower()
        ]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return None
    names = ", ".join(f"{d.name} ({d.id})" for d in hits[:10])
    raise CliError(f"'{q}' matches several chats: {names}. Use the id.")


async def resolve(client, q):
    if q == "me":
        return "me"
    # @username, phone, t.me link: let Telegram resolve it
    if q.startswith(("@", "+", "http", "t.me/")):
        try:
            return await client.get_input_entity(q)
        except (ValueError, errors.RPCError) as e:
            raise CliError(f"can't find '{q}': {e}")
    hit = pick(await client.get_dialogs(), q)
    if hit:
        return hit.input_entity
    raise CliError(f"no chat matches '{q}' (try @username or the id from `tgline chats`)")


# ---------- commands ----------

async def cmd_chats(c, a):
    async for d in c.iter_dialogs(limit=a.limit, archived=a.archived):
        if a.json:
            print(json.dumps({"id": d.id, "name": d.name, "unread": d.unread_count,
                              "username": getattr(d.entity, "username", None),
                              "kind": "user" if d.is_user else "group" if d.is_group else "channel"},
                             ensure_ascii=False))
        else:
            unread = f"[{d.unread_count}]" if d.unread_count else ""
            user = getattr(d.entity, "username", None)
            print(f"{d.id:>15}  {unread:>6}  {d.name}" + (f"  @{user}" if user else ""))


async def cmd_read(c, a):
    ent = await resolve(c, a.chat)
    msgs = await c.get_messages(ent, limit=a.limit, search=a.search)
    for m in reversed(msgs):
        emit(m, a.json)
    if a.mark and msgs:
        await c.send_read_acknowledge(ent, msgs[0])


async def cmd_send(c, a):
    text = " ".join(a.text)
    if text in ("", "-"):
        if sys.stdin.isatty() and text == "":
            raise CliError("nothing to send (give text, or pipe it in)")
        text = sys.stdin.read()
    if not text.strip():
        raise CliError("message is empty")
    m = await c.send_message(await resolve(c, a.chat), text, reply_to=a.reply)
    print(f"sent #{m.id}")


async def cmd_file(c, a):
    for p in a.paths:
        if not Path(p).is_file():
            raise CliError(f"no such file: {p}")
    m = await c.send_file(await resolve(c, a.chat), a.paths if len(a.paths) > 1 else a.paths[0],
                          caption=a.caption or "", force_document=a.document)
    ids = [x.id for x in m] if isinstance(m, list) else [m.id]
    print("sent " + " ".join(f"#{i}" for i in ids))


async def cmd_download(c, a):
    m = await c.get_messages(await resolve(c, a.chat), ids=a.id)
    if not m or not m.media:
        raise CliError(f"message #{a.id} has no media")
    print(await m.download_media(file=a.out))


async def cmd_watch(c, a):
    chats = [await resolve(c, q) for q in a.chats] or None

    @c.on(events.NewMessage(chats=chats))
    async def _(ev):
        await ev.get_sender()
        chat = utils.get_display_name(await ev.get_chat())
        emit(ev.message, a.json, chat)

    print("watching... Ctrl+C to stop", file=sys.stderr)
    await c.run_until_disconnected()


async def cmd_whoami(c, a):
    me = await c.get_me()
    print(f"{utils.get_display_name(me)}  id={me.id}" + (f"  @{me.username}" if me.username else ""))


async def cmd_logout(c, a):
    await c.log_out()
    print("logged out")


COMMANDS = {}


def build_parser():
    p = argparse.ArgumentParser(prog="tgline", description="Telegram in your terminal.")
    p.add_argument("--version", action="version", version=f"tgline {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="command")

    def add(name, fn, help, aliases=()):
        sp = sub.add_parser(name, help=help, aliases=list(aliases))
        for n in (name, *aliases):
            COMMANDS[n] = fn
        return sp

    add("login", None, "log in (phone, code, 2FA)")
    add("shell", None, "interactive mode (default)")
    s = add("chats", cmd_chats, "list chats", ["dialogs"])
    s.add_argument("-n", "--limit", type=int, default=30)
    s.add_argument("-a", "--archived", action="store_true", help="archived chats")
    s.add_argument("--json", action="store_true")
    s = add("read", cmd_read, "show messages of a chat", ["history"])
    s.add_argument("chat", help="name, @username, +phone, id or 'me'")
    s.add_argument("-n", "--limit", type=int, default=20)
    s.add_argument("-s", "--search", help="only messages containing this")
    s.add_argument("-m", "--mark", action="store_true", help="mark as read")
    s.add_argument("--json", action="store_true")
    s = add("send", cmd_send, "send a text message ('-' or pipe = stdin)", ["msg"])
    s.add_argument("chat")
    s.add_argument("text", nargs="*")
    s.add_argument("-r", "--reply", type=int, metavar="ID", help="reply to message id")
    s = add("file", cmd_file, "send files / photos", ["send-file"])
    s.add_argument("chat")
    s.add_argument("paths", nargs="+")
    s.add_argument("-c", "--caption")
    s.add_argument("-d", "--document", action="store_true", help="send as file, no compression")
    s = add("download", cmd_download, "download media of a message", ["dl"])
    s.add_argument("chat")
    s.add_argument("id", type=int)
    s.add_argument("-o", "--out", default=".", help="folder or file path")
    s = add("watch", cmd_watch, "stream new messages (all chats or given ones)")
    s.add_argument("chats", nargs="*")
    s.add_argument("--json", action="store_true")
    add("whoami", cmd_whoami, "show the logged-in account", ["me"])
    add("logout", cmd_logout, "end this session")
    return p


# ---------- shell ----------

SHELL_HELP = """\
commands: chats | read CHAT [-n 50] | send CHAT text | file CHAT path | dl CHAT ID
          open CHAT  -> chat mode: every line is sent there, /cmd runs a command, /close leaves
          whoami | help | quit
CHAT = name (part is fine), @username, +phone, id, or 'me'. New messages show up live."""


async def shell(c, parser):
    try:
        import readline  # noqa: F401  (history + arrows)
    except ImportError:
        pass
    loop = asyncio.get_running_loop()
    current = {"ent": None, "name": None}

    def prompt():
        return f"{current['name']}> " if current["name"] else "tg> "

    @c.on(events.NewMessage(incoming=True))
    async def _(ev):
        await ev.get_sender()
        chat = utils.get_display_name(await ev.get_chat())
        print(f"\r\033[K{fmt(ev.message, chat)}\n{prompt()}", end="", flush=True)

    print(SHELL_HELP)
    while True:
        try:
            line = (await loop.run_in_executor(None, input, prompt())).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if current["ent"] and not line.startswith("/"):
            try:
                await c.send_message(current["ent"], line)
            except errors.RPCError as e:
                print(f"error: {e}")
            continue
        line = line.removeprefix("/")
        if line in ("quit", "exit", "q"):
            return
        if line in ("help", "?"):
            print(SHELL_HELP)
            continue
        try:
            argv = shlex.split(line)
        except ValueError as e:
            print(f"error: {e}")
            continue
        try:
            if argv[0] == "close":
                current.update(ent=None, name=None)
                continue
            if argv[0] == "open" and len(argv) > 1:
                q = " ".join(argv[1:])
                current["ent"] = await resolve(c, q)
                current["name"] = utils.get_display_name(await c.get_entity(current["ent"]))
                for m in reversed(await c.get_messages(current["ent"], limit=10)):
                    print(fmt(m))
                continue
            if argv[0] in ("login", "shell", "logout", "watch"):
                print(f"'{argv[0]}' is not available inside the shell")
                continue
            a = parser.parse_args(argv)
            await COMMANDS[a.cmd](c, a)
        except SystemExit:  # argparse error / --help already printed
            pass
        except (CliError, errors.RPCError, ValueError) as e:
            print(f"error: {e}")


# ---------- main ----------

async def login(c):
    await c.start(
        phone=lambda: input("Phone number (international, e.g. +380...): "),
        password=lambda: getpass.getpass("2FA password: "),
        code_callback=lambda: input("Code from Telegram: "),
    )
    me = await c.get_me()
    print(f"logged in as {utils.get_display_name(me)}")


async def amain(argv):
    parser = build_parser()
    a = parser.parse_args(argv)
    cmd = a.cmd or "shell"
    interactive = sys.stdin.isatty()
    c = make_client(interactive=cmd in ("login", "shell") and interactive)
    await c.connect()  # not `async with`: that would prompt for a phone in scripts
    try:
        await run(c, a, cmd, parser, interactive)
    finally:
        await c.disconnect()


async def run(c, a, cmd, parser, interactive):
    if not await c.is_user_authorized():
        if cmd in ("login", "shell") and interactive:
            await login(c)
        else:
            raise CliError("not logged in. Run: tgline login")
    elif cmd == "login":
        await cmd_whoami(c, a)
        return
    if cmd == "shell":
        await shell(c, parser)
    elif cmd != "login":
        await COMMANDS[cmd](c, a)


def main():
    try:
        asyncio.run(amain(sys.argv[1:]))
    except CliError as e:
        sys.exit(f"tgline: {e}")
    except errors.RPCError as e:
        sys.exit(f"tgline: telegram error: {e}")
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:  # `tgline read x | head`
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


if __name__ == "__main__":
    main()
