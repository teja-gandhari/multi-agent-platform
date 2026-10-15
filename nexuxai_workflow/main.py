"""CLI entry point and stable integration exports for NexusAI."""
import sys
from workflow import (
    main, run_workflow, run_workflow_async, submit_workflow_background,
    build_initial_state, app,
)

__all__ = ["run_workflow", "run_workflow_async", "submit_workflow_background", "build_initial_state", "app"]

if __name__ == "__main__":
    sys.exit(main())
