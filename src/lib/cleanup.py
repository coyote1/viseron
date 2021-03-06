import datetime
import logging
import os
import time

from apscheduler.schedulers.background import BackgroundScheduler
from const import CAMERA_SEGMENT_DURATION
from path import Path

LOGGER = logging.getLogger(__name__)
logging.getLogger("apscheduler.scheduler").setLevel(logging.ERROR)
logging.getLogger("apscheduler.executors").setLevel(logging.ERROR)


class Cleanup:
    def __init__(self, config):
        self.directory = config.recorder.folder

        if config.recorder.retain is None:
            self.days_to_retain = 7
            LOGGER.error(
                "Number of days to retain recordings is not specified. Defaulting to 7"
            )
        else:
            self.days_to_retain = config.recorder.retain

        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._scheduler.add_job(self.cleanup, "cron", hour="1")

    def cleanup(self):
        LOGGER.debug("Running cleanup")
        retention_period = time.time() - (self.days_to_retain * 24 * 60 * 60)
        dirs = Path(self.directory)

        extensions = ["*.mp4", "*.jpg"]
        for extension in extensions:
            files = dirs.walkfiles(extension)
            for file in files:
                if file.mtime <= retention_period:
                    LOGGER.debug(f"Removing file {file}")
                    file.remove()

        folders = dirs.walkdirs("*-*-*")
        for folder in folders:
            LOGGER.debug(f"Items in {folder}: {len(folder.listdir())}")
            for subdir in folder.listdir():
                if os.path.isdir(subdir) and len(subdir.listdir()) == 0:
                    try:
                        os.rmdir(subdir)
                        LOGGER.debug(f"Removing directory {subdir}")
                    except OSError:
                        LOGGER.error(f"Could not remove directory {subdir}")

            if len(folder.listdir()) == 0:
                try:
                    folder.rmdir()
                    LOGGER.debug(f"Removing directory {folder}")
                except OSError:
                    LOGGER.error(f"Could not remove directory {folder}")

    def start(self):
        self._scheduler.start()


class SegmentCleanup:
    def __init__(self, config):
        self._directory = os.path.join(
            config.recorder.segments_folder, config.camera.name
        )
        # Make sure we dont delete a segment which is needed by recorder
        self._max_age = config.recorder.lookback + (CAMERA_SEGMENT_DURATION * 3)
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._scheduler.add_job(
            self.cleanup,
            "interval",
            seconds=CAMERA_SEGMENT_DURATION,
            id="segment_cleanup",
        )
        self._scheduler.start()

    def cleanup(self):
        now = datetime.datetime.now().timestamp()
        for segment in os.listdir(self._directory):
            start_time = datetime.datetime.strptime(
                segment.split(".")[0], "%Y%m%d%H%M%S"
            ).timestamp()
            if now - start_time > self._max_age:
                os.remove(os.path.join(self._directory, segment))

    def start(self):
        LOGGER.debug("Starting segment cleanup")
        self._scheduler.start()

    def pause(self):
        LOGGER.debug("Pausing segment cleanup")
        self._scheduler.pause_job("segment_cleanup")

    def resume(self):
        LOGGER.debug("Resuming segment cleanup")
        self._scheduler.resume_job("segment_cleanup")
