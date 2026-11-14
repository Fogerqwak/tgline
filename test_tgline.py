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
print("ok")
