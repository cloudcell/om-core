# Contributing to OM Core

Thank you for your interest in contributing to OM Core.

OM Core is an early-stage multidimensional modeling engine. The project is
intended to be useful, understandable, and technically reliable before it
becomes large. Small, well-scoped contributions are preferred.

## Project Status

OM Core is alpha software. Public APIs, file formats, commands, and internal
module boundaries may change before a stable release.

Please do not assume that a current internal implementation detail is permanent.

## Before You Contribute

Before opening a pull request, please:

1. Check existing issues and pull requests.
2. Keep the change focused.
3. Add or update tests where appropriate.
4. Update documentation if the behavior visible to users changes.
5. Avoid mixing refactoring, formatting, and feature work in one pull request.

If you are unsure whether a change fits the project direction, open an issue first.

## Development Setup

A typical local setup is:

```bash
git clone https://github.com/cloudcell/om-core.git
cd om-core

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

If the repository later provides `pyproject.toml`, prefer the documented
editable install command in the README.

## Running Tests

Use the project test script if available:

```bash
./test.sh
```

or run pytest directly:

```bash
pytest
```

Pull requests should keep the test suite passing.

## Code Style

Prefer code that is:

- explicit rather than clever
- deterministic where possible
- easy to test
- careful about public API boundaries
- conservative about dependencies

Avoid broad architectural rewrites unless they have been discussed first.

## Commit Messages

Use clear commit messages. A good commit message explains what changed and why.

Examples:

```text
Add rule evaluation test for grouped dimensions
Fix persistence round-trip for cube metadata
Document basic dimension and cube concepts
```

## Contributor Sign-off and CLA

Contributions require contributor sign-off.

Small individual contributions may use the lightweight contributor sign-off
process described in:

```text
legal/CONTRIBUTOR-SIGNOFFS.md
```

For substantial contributions, corporate contributions, or contributions where
Cloudcell Limited requests it, a signed contributor license agreement may be
required:

```text
legal/CONTRIBUTOR-CLA.md
```

By contributing, you represent that you have the right to submit the
contribution and that your contribution does not knowingly violate third-party
rights.

## License of Contributions

Unless otherwise agreed in writing, contributions to OM Core are submitted under
the same license terms that apply to the project, together with the contributor
grant described in the contributor sign-off or CLA documents.

OM Core is distributed under the GNU Affero General Public License v3.0 unless
otherwise stated.

## Trademarks

The software license does not grant trademark rights.

Use of the `OM Core` name and related marks is governed separately by:

```text
legal/TRADEMARKS.md
```

## Security Issues

Please do not report security vulnerabilities through public GitHub issues.

See:

```text
SECURITY.md
```

## Maintainer Discretion

Maintainers may decline contributions that are out of scope, too large to review
safely, insufficiently tested, inconsistent with project direction, or likely to
create long-term maintenance burden.

This is especially important while OM Core is still alpha software.
