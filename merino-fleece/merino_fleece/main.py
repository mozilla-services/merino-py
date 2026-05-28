"""Entry point for merino-fleece. Starts the FastAPI app with uvicorn."""

import uvicorn

from merino_fleece.app import create_app


app = create_app()


def main() -> None:
    """Run the merino-fleece FastAPI app via uvicorn.

    Note: this is provided as a shortcut to run merino-fleece for local development
    and profiling.
    """
    uvicorn.run(
        "merino_fleece.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
    )


if __name__ == "__main__":
    main()
