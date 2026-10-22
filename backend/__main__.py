"""Production-friendly Uvicorn entry point honoring the host-provided PORT."""

import uvicorn

from backend.app.config import get_port


def main() -> None:
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=get_port(),
    )


if __name__ == "__main__":
    main()
