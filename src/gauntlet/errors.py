class GauntletError(Exception):
    """An actionable failure with a stable CLI exit status."""

    def __init__(self, message: str, code: int = 1, check: str | None = None):
        super().__init__(message)
        self.code = code
        self.check = check
