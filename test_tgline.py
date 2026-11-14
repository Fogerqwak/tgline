"""Run: python test_tgline.py  (no network, no account needed)"""
from types import SimpleNamespace as D

import tgline

dialogs = [D(id=1, name="Mom"), D(id=2, name="Work Chat"), D(id=-100500, name="Work News"),
           D(id=4, name="Momentum")]

assert tgline.pick(dialogs, "mom").id == 1            # exact name beats partial
assert tgline.pick(dialogs, "chat").id == 2           # partial, single hit
assert tgline.pick(dialogs, "-100500").id == -100500  # id
assert tgline.pick(dialogs, "nobody") is None
try:
    tgline.pick(dialogs, "work")
    raise AssertionError("should be ambiguous")
except tgline.CliError as e:
    assert "Work Chat" in str(e) and "Work News" in str(e)

p = tgline.build_parser()
a = p.parse_args(["send", "Mom", "hi", "there", "-r", "5"])
assert (a.cmd, a.chat, a.text, a.reply) == ("send", "Mom", ["hi", "there"], 5)
assert tgline.COMMANDS["msg"] is tgline.cmd_send
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
assert abs((now - tgline.parse_since("2h")) - timedelta(hours=2)) < timedelta(seconds=5)
assert abs((now - tgline.parse_since("1w")) - timedelta(weeks=1)) < timedelta(seconds=5)
assert tgline.parse_since("2026-11-14").tzinfo is not None
try:
    tgline.parse_since("yesterday")
    raise AssertionError("should reject")
except Exception as e:
    assert "30m" in str(e)

import os, tempfile
tgline.CONFIG = tgline.Path(tempfile.mkdtemp()) / "config.json"
tgline.HOME = tgline.CONFIG.parent
os.environ.pop("TGLINE_READ_ONLY", None)
tgline.guard(p.parse_args(["send", "me", "x"]))       # off: allowed
import asyncio
asyncio.run(tgline.cmd_lock(None, None))
for argv in (["send", "me", "x"], ["file", "me", "a"], ["read", "me", "-m"], ["logout"]):
    try:
        tgline.guard(p.parse_args(argv))
        raise AssertionError(f"{argv} not blocked")
    except tgline.CliError:
        pass
tgline.guard(p.parse_args(["read", "me", "--since", "1d"]))  # reading still ok
print("ok")
