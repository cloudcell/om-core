"""
CLI interface for OpenM commands.

Provides command-line access to the command system.
Can be run standalone or integrated into the main app.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from ..core.registry import CommandRegistry, get_registry, CommandCategory
from ..core.executor import CommandExecutor, get_executor, ExecutionContext
from ..core.bootstrap import register_default_commands


def setup_parser() -> argparse.ArgumentParser:
    """Set up the argument parser."""
    parser = argparse.ArgumentParser(
        prog='openm-cmd',
        description='OpenM Command Line Interface'
    )

    subparsers = parser.add_subparsers(dest='action', help='Available commands')

    # List commands
    list_parser = subparsers.add_parser('list', help='List available commands')
    list_parser.add_argument('--category', '-c', choices=[c.name.lower() for c in CommandCategory],
                            help='Filter by category')
    list_parser.add_argument('--search', '-s', help='Search pattern')

    # Execute command
    exec_parser = subparsers.add_parser('exec', help='Execute a command')
    exec_parser.add_argument('command_id', help='Command ID to execute')
    exec_parser.add_argument('params', nargs='*', help='Parameters as key=value pairs')

    # Interactive mode
    subparsers.add_parser('interactive', help='Start interactive REPL')

    return parser


def parse_params(params: list[str]) -> dict:
    """Parse key=value pairs into dict."""
    result = {}
    for param in params:
        if '=' in param:
            key, value = param.split('=', 1)
            # Try to infer type
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    if value.lower() in ('true', 'yes'):
                        value = True
                    elif value.lower() in ('false', 'no'):
                        value = False
            result[key] = value
        else:
            # Positional args become sequential params
            result[f'arg{len(result)}'] = param
    return result


def cmd_list(registry: CommandRegistry, args) -> int:
    """Handle the 'list' subcommand."""
    if args.category:
        category = CommandCategory[args.category.upper()]
        commands = registry.get_by_category(category)
        print(f"\n{category.name} Commands:")
    else:
        commands = registry.get_all()
        print("\nAll Commands:")

    if args.search:
        pattern = args.search.lower()
        commands = {
            k: v for k, v in commands.items()
            if pattern in k.lower() or pattern in v.name.lower()
        }

    if not commands:
        print("  No commands found")
        return 0

    # Group by category for display
    by_category: dict[CommandCategory, list] = {}
    for cmd_id, cmd in sorted(commands.items()):
        if cmd.category not in by_category:
            by_category[cmd.category] = []
        by_category[cmd.category].append(cmd)

    for cat, cmds in sorted(by_category.items(), key=lambda x: x[0].name):
        print(f"\n  [{cat.name}]")
        for cmd in cmds:
            shortcut = f" ({cmd.shortcut})" if cmd.shortcut else ""
            print(f"    {cmd.id:<25} {cmd.name}{shortcut}")
            if cmd.description:
                print(f"      {cmd.description}")

    return 0


def cmd_exec(executor: CommandExecutor, args) -> int:
    """Handle the 'exec' subcommand."""
    params = parse_params(args.params)

    result = executor.execute(args.command_id, **params)

    if result.status.name == "NOT_FOUND":
        print(f"Error: Command '{args.command_id}' not found")
        return 1

    if result.status.name == "ERROR":
        print(f"Error: {result.error}")
        return 1

    print(f"Executed '{args.command_id}' in {result.duration_ms:.1f}ms")
    if result.data:
        print(f"Result: {result.data}")

    return 0


def cmd_interactive() -> int:
    """Start the interactive REPL."""
    from .repl import OpenMREPL
    repl = OpenMREPL()
    repl.run()
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the CLI."""
    # Register default commands on startup
    register_default_commands()

    parser = setup_parser()
    args = parser.parse_args(argv)

    if args.action is None:
        parser.print_help()
        return 0

    registry = get_registry()
    executor = get_executor()

    # Setup minimal context for CLI
    context = ExecutionContext()
    executor.set_context(context)

    if args.action == 'list':
        return cmd_list(registry, args)
    elif args.action == 'exec':
        return cmd_exec(executor, args)
    elif args.action == 'interactive':
        return cmd_interactive()

    return 0


if __name__ == '__main__':
    sys.exit(main())
