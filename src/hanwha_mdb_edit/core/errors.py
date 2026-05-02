"""Domain errors for Hanwha MDB editing."""


class HanwhaEditError(RuntimeError):
    """Base error for validation or IO in hanwha_mdb_edit core."""


class HanwhaValidationError(HanwhaEditError):
    """PART_Det row failed field validation."""


class HanwhaSaveError(HanwhaEditError):
    """Could not persist PART_Det (Jet write or export failed)."""
