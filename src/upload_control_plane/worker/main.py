import logging
import time

from upload_control_plane.config import get_settings


def run() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logging.getLogger(__name__).info(
        "worker scaffold started; lifecycle automation is not implemented in T00"
    )

    while True:
        time.sleep(60)


if __name__ == "__main__":
    run()
