import logging
import sys


RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
GRAY = "\033[90m"
WHITE = "\033[97m"


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": GRAY,
        "INFO": CYAN,
        "WARNING": YELLOW,
        "ERROR": RED,
        "CRITICAL": MAGENTA,
    }

    def format(self, record):
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{RESET}"
        record.name = f"{BLUE}{record.name}{RESET}" if record.name else ""
        return super().format(record)


def get_logger(name: str = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = ColoredFormatter(
            fmt=f"{GRAY}%(asctime)s{RESET} | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def setup_root_logger(level: int = logging.INFO):
    logging.root.setLevel(level)
    if not logging.root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = ColoredFormatter(
            fmt=f"{GRAY}%(asctime)s{RESET} | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logging.root.addHandler(handler)


def log_section(title: str, color: str = CYAN):
    print(f"\n{color}{'='*50}{RESET}")
    print(f"{color} {title} {RESET}")
    print(f"{color}{'='*50}{RESET}\n")


def log_step(step: str, color: str = BLUE):
    print(f"\n{color}[Step]{RESET} {step}")


def log_success(message: str):
    print(f"{GREEN}✓ {message}{RESET}")


def log_error(message: str):
    print(f"{RED}✗ {message}{RESET}")


def log_info(message: str):
    print(f"{CYAN}ℹ {message}{RESET}")


def log_warning(message: str):
    print(f"{YELLOW}⚠ {message}{RESET}")


setup_root_logger()
