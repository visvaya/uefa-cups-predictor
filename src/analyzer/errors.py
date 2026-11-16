"""The analyzer's error for inputs it cannot work with."""


class AnalyzerInputError(Exception):
    """An input the analyzer cannot work with; the CLI prints it as `ERROR: <message>` and exits with code 1."""
