"""
Studio Validator - CLI Entry Point

Allows running the package as: python -m studio

@cpt-flow:cpt-studio-flow-core-infra-cli-invocation:p1
"""

import sys

# Import main from parent studio.py during migration
# This will be updated to import from cli.py after full migration
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from studio import main

if __name__ == "__main__":
    raise SystemExit(main())
