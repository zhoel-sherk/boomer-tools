"""Editable PART_Det rows with Jet Text(n) length limits from observed schema."""

from __future__ import annotations

from dataclasses import dataclass

from hanwha_mdb_edit.core.errors import HanwhaValidationError

# From mdb-schema PART_Det (Hanwha UPD sample).
MAX_PARTNAME_LEN = 32
MAX_PROFILENAME_LEN = 50
MAX_PARTDESC_LEN = 255


@dataclass
class EditablePartDetRow:
    partname: str
    profilename: str
    partdesc: str
    confidence_level: int
    used_machine_set: int
    vendor_id: int = 0

    def validate(self) -> None:
        if len(self.partname) > MAX_PARTNAME_LEN:
            raise HanwhaValidationError(f"PARTNAME exceeds {MAX_PARTNAME_LEN} characters.")
        if len(self.profilename) > MAX_PROFILENAME_LEN:
            raise HanwhaValidationError(f"PROFILENAME exceeds {MAX_PROFILENAME_LEN} characters.")
        if len(self.partdesc) > MAX_PARTDESC_LEN:
            raise HanwhaValidationError(f"PARTDESC exceeds {MAX_PARTDESC_LEN} characters.")
