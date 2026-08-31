# Working in the monorepo

This repository contains several applications, shared packages, and supporting tools. Keeping
them together lets a single change update both a shared contract and every consumer that relies on
it. The repository is still divided into projects so that an unrelated change does not need to
build, test, or eventually deploy everything.

Moon describes those project boundaries and the relationships between them. It provides one
consistent way to run established project tasks, works out which projects are affected by a
change, orders dependent work, and caches safe results. It does not replace the native build and
package tools used by each language.

## Which tool should I use?

| Tool | Responsibility | Typical use |
| --- | --- | --- |
| Moon | Repository-wide project graph and repeatable tasks | Run lint or tests for one or many projects |
| `uv` | Python environments, dependencies, workspace packages, and `uv.lock` | Add a Python dependency, sync the environment, or run an ad hoc Python command |
| Cargo | Rust dependencies, compilation, and tests for future Rust projects | Add a crate or run a crate-specific Cargo command |
| Make | Compatibility commands during the migration | Use an existing workflow that has not moved to Moon yet |

Use Moon when the operation is a named repository task or spans projects. Use `uv` or Cargo when
managing dependencies or doing language-specific investigation. Moon tasks call those native tools
underneath, so there is only one dependency definition and one lockfile per ecosystem.

## Install Moon

Moon is a local CLI. Its version is pinned in `.prototools`, but that file does not install either
Moon or its version manager automatically.

### One-time machine setup

Install [proto](https://moonrepo.dev/docs/proto/install) once on your machine. For Bash or Zsh:

```bash
bash <(curl -fsSL https://moonrepo.dev/install/proto.sh)
```

For Fish:

```fish
bash (curl -fsSL https://moonrepo.dev/install/proto.sh | psub)
```

Follow the installer's prompt to add `~/.proto/bin` to your `PATH`, then restart your shell. You do
not install Moon through Homebrew. Proto requires Git and common archive utilities; see the proto
installation documentation if any of those prerequisites are missing.

### Repository setup

After cloning the repository, run:

```bash
proto install
moon --version
```

`proto install` reads `.prototools` and installs the repository's pinned Moon version without
changing the version used by other repositories. A developer who does not run Moon commands does
not need the CLI, but commands such as `make moon-test` and `moon run merino:test` require it.

Every Python task depends on one repository-level install task. That task runs `uv sync --frozen`
once before Moon starts parallel work. The project tasks then invoke `uv run --frozen --no-sync`,
so they never compete to update the shared virtual environment.

## Projects and dependencies

| Project | Directory | Depends on |
| --- | --- | --- |
| `workspace` | Repository root | None |
| `merino` | `apps/merino` | `merino-common` |
| `fleece` | `apps/fleece` | `merino-common` |
| `merino-common` | `packages/merino-common` | None |
| `load-tests` | `tools/load-tests` | `merino`, `merino-common` |
| `docs` | `docs` | None |

The load-test dependency is intentional: its Locust code imports Merino and common internals.
Fleece and Merino do not depend on each other merely because they communicate at runtime.

Inspect a project or the complete graph with:

```bash
moon project merino
moon project-graph
```

## Run tasks

Run a task for one project:

```bash
moon run merino:test
moon run fleece:typecheck
moon run load-tests:validate
```

Run a task in every project that defines it:

```bash
moon run :test
```

Run all linting, formatting checks, security checks, and type checking:

```bash
moon run ':#quality'
```

From anywhere inside a project, `~` means the closest project:

```bash
moon run '~:test'
```

Arguments after `--` are forwarded to the underlying command. For example:

```bash
moon run merino:test -- -k query_normalization
```

Moon runs tasks from the workspace root because parts of the current Python runtime and test suite
resolve files relative to that directory. Project inputs still define the boundary used for
caching and affected-project decisions.

## Python dependency changes

Continue using `uv`; Moon does not edit Python manifests or the lockfile:

```bash
uv add --package merino <dependency>
uv remove --package merino <dependency>
uv lock
uv sync --all-groups --all-packages
```

The root `uv.lock` is shared by all Python projects. A lockfile or root Python configuration change
therefore affects every Python project by design.
