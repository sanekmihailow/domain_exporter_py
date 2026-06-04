"""Make the project root importable so tests can `import config`, etc.

The exporter modules use flat top-level imports (`import config`,
`import rdap_router`); placing this conftest at the repo root puts that root
on ``sys.path`` for the whole test session.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
