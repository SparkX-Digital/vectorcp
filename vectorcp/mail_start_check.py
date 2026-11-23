#!/usr/bin/python3
"""Standalone native unit gate. An inaccessible checkpoint is a startup error."""
import os
from pathlib import Path
import stat


def check(base=Path('/var/lib/vectorcp-mail'), queue=Path('/var/spool/postfix')):
    if not os.path.ismount(base / 'store') or not os.path.ismount(queue):
        raise RuntimeError('The bounded mail storage and queue must both be mounted.')
    try:
        (base / 'pending.json').lstat()
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError('Owner recovery is required for the pending mail publication.')
    # Other OSErrors deliberately propagate: permission errors cannot mean absent.
    info = (base / 'lookup.sqlite3').lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o027:
        raise RuntimeError('The root-owned mail lookup is missing or has unsafe permissions.')


if __name__ == '__main__':
    try:
        check()
    except (OSError, RuntimeError) as error:
        raise SystemExit(str(error))
