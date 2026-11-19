"""Tests for the local ledger - atomicity, defaults, crash recovery."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from ledger import Ledger  # noqa: E402


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}{(' -> ' + detail) if detail and not condition else ''}")
    return condition


results = []

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "state.json")

    # 1. defaults are used for a fresh file
    db = Ledger(path, default={"cash": 500.0, "trades": []})
    results.append(check("fresh ledger uses defaults", db.data == {"cash": 500.0, "trades": []}, str(db.data)))
    results.append(check("no file until first save", not os.path.exists(path)))
    db.save()
    results.append(check("file written on save", os.path.exists(path)))

    # 2. get / set / append
    db.set("cash", 432.5)
    results.append(check("set persists", Ledger(path).get("cash") == 432.5))
    db.append("trades", {"sym": "ITC", "qty": 1})
    db.append("trades", {"sym": "YESBANK", "qty": 2})
    results.append(check("append works", len(Ledger(path).get("trades")) == 2))

    # 3. update() mutates atomically
    db.update(lambda s: s.__setitem__("cash", s["cash"] - 100))
    results.append(check("update mutates + saves", Ledger(path).get("cash") == 332.5))

    # 4. defaults are merged with existing keys
    db2 = Ledger(path, default={"cash": 500.0, "trades": [], "new_key": "added"})
    results.append(check("new default keys merged in", db2.get("new_key") == "added"))
    results.append(check("existing values preserved", db2.get("cash") == 332.5))

    # 5. corrupt file does not crash - falls back to defaults
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json")
    db3 = Ledger(path, default={"cash": 500.0, "trades": []})
    results.append(check("corrupt file -> defaults", db3.data == {"cash": 500.0, "trades": []}, str(db3.data)))

    # 6. no leftover temp files after writes
    leftovers = [f for f in os.listdir(tmp) if f.startswith(".ledger_")]
    results.append(check("no temp files left behind", not leftovers, str(leftovers)))

    # 7. reset
    db3.set("cash", 1.0)
    db3.reset()
    results.append(check("reset restores defaults", Ledger(path).get("cash") == 500.0))

    # 8. nested directories are created
    nested = os.path.join(tmp, "deep", "dir", "state.json")
    Ledger(nested, default={"a": 1}).save()
    results.append(check("nested path created", os.path.exists(nested)))

    # 9. append to a non-list raises
    db4 = Ledger(os.path.join(tmp, "x.json"), default={"n": 5})
    try:
        db4.append("n", 1)
        results.append(check("append to non-list rejected", False))
    except TypeError:
        results.append(check("append to non-list rejected", True))

print()
print(f"{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
