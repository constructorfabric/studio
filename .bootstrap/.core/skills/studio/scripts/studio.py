#!/usr/bin/env python3
"""
Studio Validator - Main Entry Point

This is a thin wrapper that imports from the modular studio package.
For backward compatibility, all functions are re-exported at module level.

Legacy monolithic implementation preserved in legacy.py.
"""

# Re-export everything from the studio package for backward compatibility
from studio import *
from studio import __all__

# CLI entry point
if __name__ == "__main__":
    from studio import main
    raise SystemExit(main())
