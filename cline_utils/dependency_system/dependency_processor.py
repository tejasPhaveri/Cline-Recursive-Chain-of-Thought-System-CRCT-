"""
Lightweight entry point for dependency system commands.
Delegates to flow modules or core operations for execution.
"""

import argparse
import sys
# Import flow modules
from cline_utils.dependency_system.flows.setup import register_parser as register_setup
from cline_utils.dependency_system.flows.suggest_dependencies_flow import register_parser as register_suggest
# Add to imports at the top
from cline_utils.dependency_system.core.exceptions import TrackerError

# Import core modules for manual tracker management
from cline_utils.dependency_system.core.dependency_grid import (
    register_parser as register_grid,
    add_dependency_to_grid,
    remove_dependency_from_grid,
    get_dependencies_from_grid,
)
from cline_utils.dependency_system.io.tracker_io import read_tracker_file, write_tracker_file

# Add this import at the top of dependency_processor.py
import logging
logger = logging.getLogger(__name__)


def main():
    """
    Parse command-line arguments and dispatch to the appropriate handler.
    
    This is the main entry point for the dependency system CLI. It sets up
    the argument parser, registers all available commands from the flow modules
    and core operations, and dispatches the command to the appropriate handler.
    
    Returns:
        The exit code from the command handler (0 for success, non-zero for error)
    """

    parser = argparse.ArgumentParser(description="Dependency System CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Register flow commands
    register_setup(subparsers)
    register_suggest(subparsers)

    # Register manual tracker management commands
    register_grid(subparsers)  # For add-dependency

    # Additional manual commands
    remove_parser = subparsers.add_parser("remove-dependency", help="Remove a dependency between two keys")
    remove_parser.add_argument("source_key", help="Source key")
    remove_parser.add_argument("target_key", help="Target key")
    remove_parser.add_argument("--tracker-file", required=True, help="Path to tracker file")
    remove_parser.set_defaults(func=remove_dependency)

    show_parser = subparsers.add_parser("show-dependencies", help="Show dependencies for a key")
    show_parser.add_argument("key", help="Key to query")
    show_parser.add_argument("--tracker-file", required=True, help="Path to tracker file")
    show_parser.add_argument("--direction", default="outgoing", choices=["outgoing", "incoming"], help="Dependency direction")
    show_parser.set_defaults(func=show_dependencies)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    return args.func(args)

def remove_dependency(args):
    """Remove a dependency from the tracker."""
    try:
        tracker_data = read_tracker_file(args.tracker_file)
        if not tracker_data:
            logger.error(f"Failed to read tracker file {args.tracker_file}")
            raise TrackerError(f"Failed to read tracker file {args.tracker_file}")

        keys = list(tracker_data["keys"].keys())
        grid = tracker_data["grid"]
        updated_grid = remove_dependency_from_grid(grid, args.source_key, args.target_key, keys)
        success = write_tracker_file(args.tracker_file, tracker_data["keys"], updated_grid, tracker_data.get("last_key_edit", ""))
        if success:
            print(f"Removed dependency: {args.source_key} -> {args.target_key}")
            return 0
        raise TrackerError(f"Failed to update tracker file")
    except TrackerError as e:
        print(f"Error: {str(e)}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        print(f"Error: Unexpected error occurred")
        return 1

def show_dependencies(args):
    """Show dependencies for a key."""
    try:
        tracker_data = read_tracker_file(args.tracker_file)
        if not tracker_data:
            logger.error(f"Failed to read tracker file {args.tracker_file}")
            raise TrackerError(f"Failed to read tracker file {args.tracker_file}")

        keys = list(tracker_data["keys"].keys())
        grid = tracker_data["grid"]
        deps = get_dependencies_from_grid(grid, args.key, keys, args.direction)
        if deps:
            print(f"Dependencies for {args.key} ({args.direction}):")
            for dep_key, dep_type in deps:
                print(f"  {args.key} {dep_type} {dep_key}")
        else:
            print(f"No {args.direction} dependencies found for {args.key}")
        return 0
    except TrackerError as e:
        print(f"Error: {str(e)}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        print(f"Error: Unexpected error occurred")
        return 1

if __name__ == "__main__":
    sys.exit(main())

# EoF