# Merino-common

A package for common reusable modules of **merino-py**.

## Code Structure

- **app_configs**, located in @merino-common/merino_common/app_configs/, provide various common application configurations.
- **routers**, located in @merino-common/merino_common/routers/, common FastAPI routers such as DockerFlow for **merino** and **merino-fleece**.
- **utiles**, located in @merino-common/merino_common/utils/, common utilities for **merino-py**.

## Package Dependencies

Dependencies for **merino-common** are managed by its own @merino-common/pyproject.toml.

## Testing

The tests of this package is located in @merino-common/tests, which can be run individually. However, since the common modules are used by other member packages, it's preferred to run the whole test suite via `make test` to test the entire project whenever a change is made here.
