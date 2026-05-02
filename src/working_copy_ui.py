"""Qt UI helpers for optional pickle snapshots (see working_copy.py)."""

from __future__ import annotations

from typing import Literal, Union

import pandas as pd
from PySide6 import QtWidgets

from working_copy import find_snapshot

Outcome = Union[pd.DataFrame, None, Literal["cancel"]]


def prompt_recover_snapshot(
    parent: QtWidgets.QWidget | None,
    path: str,
    kind: str,
    autosave_dir: str,
) -> Outcome:
    """
    If a dirty snapshot exists for ``path`` / ``kind``, ask the user.

    Returns:
        Recovered DataFrame if user chooses Recovered.
        None if user chooses Original or no dirty snapshot exists.
        \"cancel\" if user chooses Cancel.
    """
    snap = find_snapshot(path, kind, autosave_dir)
    if snap is None or not bool(snap.meta.get("dirty", False)):
        return None
    source = snap.meta.get("source") or {}
    saved_at = str(snap.meta.get("saved_at", ""))
    msg = QtWidgets.QMessageBox(parent)
    msg.setWindowTitle("Recovered working copy found")
    msg.setText(
        f"Recovered edited {kind.upper()} copy found for:\n{source.get('name', path)}\n\n"
        f"Saved at: {saved_at}\n\nOpen recovered copy or original?"
    )
    recovered_btn = msg.addButton("Recovered", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
    original_btn = msg.addButton("Original", QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
    cancel_btn = msg.addButton("Cancel", QtWidgets.QMessageBox.ButtonRole.RejectRole)
    msg.exec()
    clicked = msg.clickedButton()
    if clicked == recovered_btn:
        return snap.dataframe
    if clicked == original_btn:
        return None
    if clicked == cancel_btn:
        return "cancel"
    return "cancel"
