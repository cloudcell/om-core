# Security Policy

## Supported Versions

OM Core is currently alpha software.

At this stage, security fixes are generally applied to the current development
version only. Formal long-term support policies may be introduced after the
project reaches stable releases.

| Version | Supported |
| ------- | --------- |
| current alpha branch | Best effort |
| older unreleased snapshots | No |

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Report suspected vulnerabilities by email:

```text
alex@cloudcell.nz
```

Suggested subject:

```text
OM Core Security Report
```

Please include as much detail as reasonably possible:

- affected version, commit, or branch
- operating system and Python version
- steps to reproduce
- proof-of-concept input, file, model, script, or command if available
- expected behavior
- observed behavior
- security impact
- whether the issue is public or privately discovered

## Response Expectations

OM Core is an early-stage project, so response times are best effort.

The intended process is:

1. Acknowledge the report.
2. Reproduce and assess the issue.
3. Prepare a fix or mitigation where appropriate.
4. Credit the reporter if desired and appropriate.
5. Publish a security note if the issue affects public users.

## Scope

Security-relevant issues may include, but are not limited to:

- arbitrary code execution
- unsafe loading or parsing of model files
- path traversal
- command injection
- unsafe plugin or scripting behavior
- exposure of local files, credentials, or environment variables
- denial-of-service issues caused by malformed project/model files
- dependency vulnerabilities with practical impact on OM Core

## Out of Scope

The following are usually out of scope unless they demonstrate a concrete
security impact:

- missing hardening in alpha-only development scripts
- issues requiring already-compromised local machines
- denial-of-service from intentionally huge inputs without a specific parser or
  validation flaw
- reports generated only by automated scanners without analysis
- social engineering or phishing

## Coordinated Disclosure

Please give the maintainers a reasonable opportunity to investigate and fix
reported vulnerabilities before public disclosure.

## No Warranty

OM Core is provided without warranty. See the project license for full terms.
