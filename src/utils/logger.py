import logging
import logging.config
from pathlib import Path

import yaml


def setup_logging(config_path: str = "config/logging.yaml") -> None:
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            config = yaml.safe_load(f)
        Path("data/logs").mkdir(parents=True, exist_ok=True)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=logging.INFO)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
