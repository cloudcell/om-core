# Known Issues

This document lists known issues, limitations, and rough edges in the current
public alpha of OM Core.

OM Core is alpha software. Some of these issues may be fixed by normal
development rather than treated as stable compatibility obligations.

## General Alpha Limitations

- Public APIs are not yet stable.
- Internal module boundaries may change.
- File formats and persisted workspace structures may change before v1.0.
- Some commands, views, and UI behaviors may be renamed or reorganized.
- Error messages may be incomplete or too technical.
- Documentation may lag behind implementation.

## Installation and Environment

- The current setup is primarily intended for development use.
- Installation uses uv with the dependencies listed in `pyproject.toml` and pinned
  in `uv.lock`.
- Some platforms may require additional system packages for GUI support.
- Clean-machine setup has not yet been hardened into a packaged installer.
- Windows support may require additional testing, especially around shell
  scripts and process behavior.

## GUI and Runtime

- The GUI is part of the alpha application stack and may contain unfinished
  workflows.
- Toolbar configuration is currently loaded from the committed `.om/` directory.
- Some UI layout, toolbar, panel, or window-state behavior may change.
- GUI modules are included because the current application depends on them, but
  they should not yet be treated as stable public extension APIs.
- Timeline, rule panel, and related UI components may be reorganized before
  stable release.

## REPL, Commands, and Scripting

- The command system is still evolving.
- Some command names, arguments, or response formats may change.
- REPL workflows may expose implementation details that will be hidden or
  simplified later.
- Macro and scripting behavior may change as the public API becomes clearer.
- Backward compatibility for alpha macros is not guaranteed.

## Modeling Engine

- Core modeling concepts such as dimensions, groups, cubes, rules, and views are
  expected to remain central.
- Exact APIs and persistence representations may still change.
- Edge cases around grouping, aggregation, ordering, sparse data, and rule
  precedence may need additional tests.
- Large-model behavior is still being benchmarked and improved.
- Performance characteristics should not yet be treated as final.

## Persistence and File Compatibility

- Saved workspace formats may change during alpha.
- Forward/backward compatibility between alpha versions is not guaranteed.
- Users should keep backups of important models.
- Migration tools may be introduced later, but should not be assumed for early
  alpha files.

## Documentation

- Documentation is incomplete.
- Some examples may be more up to date than prose documentation.
- Concept documentation may not yet cover all implementation details.
- Public contributor guidance is still being refined.

## Third-Party Assets

- Third-party icons and assets are included under their own licenses.
- See `legal/THIRD-PARTY-NOTICES.md`.
- Asset paths and icon sets may change before stable release.

## Security

- OM Core has not yet undergone a formal third-party security audit.
- Plugin, scripting, file loading, and command execution surfaces should be
  treated carefully.
- Do not load untrusted project files, scripts, plugins, or macros unless you
  understand the risk.
- Security issues should be reported privately as described in `SECURITY.md`.

## Trademarks and Branding

- The `OM Core` name is governed separately from the software license.
- Forks and derivative projects should use distinct names and branding.
- See `legal/TRADEMARKS.md`.

## Reporting Issues

When reporting a bug, please include:

- the commit or version
- operating system
- Python version
- steps to reproduce
- expected behavior
- observed behavior
- relevant logs, screenshots, or example model files if available

For public bugs, use GitHub issues.

For security issues, do not open a public issue. See `SECURITY.md`.

## Not Yet Promised

The following should not be assumed in the current alpha:

- stable plugin API
- stable scripting API
- stable file format
- stable GUI extension API
- packaged desktop installer
- cloud or hosted service
- enterprise support terms
- compatibility with future commercial editions
- production readiness for critical business use without independent validation
