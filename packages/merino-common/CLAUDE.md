# Merino-common

A package for common reusable modules of **merino-py**.

## Code Structure

- **app_configs**, located in @packages/merino-common/merino_common/app_configs/, provide various common application configurations.
- **routers**, located in @packages/merino-common/merino_common/routers/, common FastAPI routers such as DockerFlow for **merino** and **merino-fleece**.
- **utils**, located in @packages/merino-common/merino_common/utils/, common utilities for **merino-py**.
- **testing**, located in @packages/merino-common/merino_common/testing/, common utilities for testing.

## Package Dependencies

Dependencies for **merino-common** are managed by its own @packages/merino-common/pyproject.toml.

## Testing

The tests of this package is located in @packages/merino-common/tests, which can be run individually. However, since the common modules are used by other member packages, it's preferred to run every project's tests via `moon run :test merino:diff-coverage` whenever a change is made here.
