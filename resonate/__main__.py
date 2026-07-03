import logging

from .bot import Resonate
from .config import Config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    config = Config.from_env()
    bot = Resonate(config)
    bot.run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
