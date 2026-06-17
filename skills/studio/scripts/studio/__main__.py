"""
Studio Validator - CLI Entry Point

Allows running the package as: python -m studio

@cpt-flow:cpt-studio-flow-core-infra-cli-invocation:p1
"""

import sys
from pathlib import Path

# Import main from parent studio.py during migration
# This will be updated to import from cli.py after full migration
sys.path.insert(0, str(Path(__file__).parent.parent))
from studio import main  # pylint: disable=wrong-import-position

if __name__ == "__main__":
    raise SystemExit(main())
