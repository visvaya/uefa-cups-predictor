"""Entry point of the analyzer: `python analyze.py [--cl] [--el] [--excel-pl] [--sr-only ...]`.

The code lives in `src/analyzer/`; this file only points it at the data next to it (`data/`) and keeps the CLI path.
"""

from pathlib import Path

from src.analyzer.cli import main

if __name__ == "__main__":
    main(Path(__file__).parent)
