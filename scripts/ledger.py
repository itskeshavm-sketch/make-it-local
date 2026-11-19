"""Local JSON ledger - the state pattern behind every local-first app.

Write-through, atomic (tmp file + os.replace), never loses data on a crash.
No dependencies.

    from ledger import Ledger
    db = Ledger("state.json", default={"cash": 500.0, "trades": []})
    db.update(lambda s: s["trades"].append({"sym": "ITC", "qty": 1}))
    print(db.data["cash"])
"""
import json
import os
import tempfile


class Ledger:
    def __init__(self, path="state.json", default=None):
        self.path = path
        self.default = default if default is not None else {}
        self.data = self.load()

    # ------------------------------------------------------------- load/save
    def load(self):
        if not os.path.exists(self.path):
            return json.loads(json.dumps(self.default))  # deep copy
        try:
            with open(self.path, encoding="utf-8-sig") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict) and isinstance(self.default, dict):
                merged = json.loads(json.dumps(self.default))
                merged.update(loaded)
                return merged
            return loaded
        except (ValueError, OSError):
            # corrupt or half-written file: keep the default, never crash
            return json.loads(json.dumps(self.default))

    def save(self, data=None):
        """Atomic write: temp file in the same directory, then replace."""
        payload = self.data if data is None else data
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".ledger_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        return self.path

    # ------------------------------------------------------------- accessors
    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, save=True):
        self.data[key] = value
        if save:
            self.save()
        return value

    def append(self, key, item, save=True):
        bucket = self.data.setdefault(key, [])
        if not isinstance(bucket, list):
            raise TypeError(f"'{key}' is not a list")
        bucket.append(item)
        if save:
            self.save()
        return bucket

    def update(self, fn, save=True):
        """Mutate the state in one atomic step:  db.update(lambda s: ...)"""
        result = fn(self.data)
        if result is not None:
            self.data = result
        if save:
            self.save()
        return self.data

    def reset(self):
        self.data = json.loads(json.dumps(self.default))
        return self.save()

    def __repr__(self):
        return f"Ledger({self.path!r}, keys={list(self.data)[:8]})"
