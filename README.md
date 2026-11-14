# tgline

Telegram in your terminal, for Linux and macOS. An interactive shell like the old
`telegram-cli`, plus one-shot commands you can pipe and script.

It talks to Telegram directly over MTProto (via [Telethon](https://github.com/LonamiWebs/Telethon)),
logged in as **you**, not a bot. No TDLib to compile, no Electron, one Python file.

```
$ tgline
tg> chats
       12345678     [2]  Mom
 -1001234567890          Work Chat  @workchat
tg> open mom
[2026-11-14 09:12] #811 Mom: are you coming for dinner?
Mom> yes, at 7
Mom> /close
tg> quit
```

## Why another one

The classic `vysheng/tg` telegram-cli has been dead for years and no longer works with
the current Telegram layer. What's alive today are full-screen TUIs
([nchat](https://github.com/d99kris/nchat), [tgt](https://github.com/FedericoBruzzone/tgt), …),
which are great for chatting but awkward in scripts and cron jobs, and most of them need TDLib built.
`tgline` aims at the gap: `pipx install`, log in, and both chat and script from the shell.

## Install

Needs Python 3.9+.

```bash
pipx install git+https://github.com/Fogerqwak/tgline
# or
uv tool install git+https://github.com/Fogerqwak/tgline
```

## Log in

1. Get your own `api_id` and `api_hash` at <https://my.telegram.org> → *API development tools*
   (any app name works). Every user uses their own keys; tgline ships none.
2. Run `tgline login` and enter the keys, your phone number, the code Telegram sends you,
   and your 2FA password if you have one.

The session lives in `~/.config/tgline/` (or `$XDG_CONFIG_HOME/tgline`, or `$TGLINE_HOME`),
readable only by you. **Anyone who gets that folder gets your account** — don't sync it publicly.
`tgline logout` ends the session; you can also kill it from Telegram → Settings → Devices.

Keys can also come from the environment: `TG_API_ID`, `TG_API_HASH`.

## Commands

A `CHAT` is a name (or part of it), `@username`, `+phone`, a numeric id from `tgline chats`, or `me`
(Saved Messages).

| command | what it does |
|---|---|
| `tgline` / `tgline shell` | interactive shell, new messages appear live |
| `tgline chats [-n 30] [-a] [--json]` | list chats with unread counts (`-a` = archived) |
| `tgline read CHAT [-n 20] [-s TEXT] [-m] [--json]` | show messages; `-s` search, `-m` mark as read |
| `tgline send CHAT text…` | send a message; `-r ID` to reply; text from stdin with `-` or a pipe |
| `tgline file CHAT path… [-c caption] [-d]` | send files/photos (`-d` = as file, no compression) |
| `tgline dl CHAT ID [-o folder]` | download the media of a message |
| `tgline watch [CHAT…] [--json]` | print new messages as they arrive (all chats if none given) |
| `tgline whoami` / `tgline logout` | account info / end session |

Reading does not send read receipts unless you pass `-m`.

In the shell, the same commands work without the `tgline` prefix. `open CHAT` enters chat mode:
every line you type is sent there, `/read`, `/file` etc. still work, `/close` leaves.

## Scripting

```bash
# notify yourself when a long job finishes
make build && tgline send me "build ok" || tgline send me "build FAILED"

# send a log tail
tail -n 50 app.log | tgline send me -

# message ids + text as JSON lines
tgline read "Work Chat" -n 100 --json | jq -r 'select(.text | test("deploy")) | .text'

# react to incoming messages
tgline watch @somebot --json | while read -r line; do echo "$line" | jq .text; done
```

Exit code is non-zero on errors, messages go to stderr.

## Development

```bash
git clone https://github.com/Fogerqwak/tgline && cd tgline
python -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python test_tgline.py
```

Not there yet: reactions, editing/deleting, secret chats, a full-screen UI.
PRs welcome.

## License

MIT
