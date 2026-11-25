"""Entry point for merino-hook-eye. Starts the FastAPI app with uvicorn."""

import uvicorn

from merino_hook_eye.app import create_app

app = create_app()


def main() -> None:
    """Run the merino-hook-eye FastAPI app via uvicorn.

    Note: this is provided as a shortcut to run merino-hook-eye for local development.
    """
    uvicorn.run(
        "merino_hook_eye.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8002,
    )


if __name__ == "__main__":
    main()
