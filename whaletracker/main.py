from __future__ import annotations

import asyncio
import logging

from .config import Settings, load_env_file
from .publisher import RedisPublisher
from .tracker import WhaleTracker


async def amain() -> None:
    load_env_file()
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings.validate()

    publisher = RedisPublisher(settings.redis_url)
    await publisher.ping()
    try:
        await WhaleTracker(publisher, settings).start()
    finally:
        await publisher.close()


def main() -> None:
    try:
        asyncio.run(amain())
    except ValueError as exc:
        raise SystemExit(f"Configuration error: {exc}") from None
    except KeyboardInterrupt:
        raise SystemExit("Stopped.")


if __name__ == "__main__":
    main()
