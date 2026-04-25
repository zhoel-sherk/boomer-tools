import logging
import os
import time

# -----------------------------------------------------------------------------

# Create a default logger if not initialized
try:
    __logger = logging.getLogger('__logger')
    __logger.setLevel(logging.DEBUG)
    # Add default handler if none exists
    if not __logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        __logger.addHandler(handler)
except:
    __logger = None

# -----------------------------------------------------------------------------

def __get_logs_directory() -> str:
    logs_path = os.path.dirname(__file__)
    logs_path = os.path.join(logs_path, "..")
    logs_path = os.path.abspath(logs_path)
    logs_path = os.path.join(logs_path, "logs")
    return logs_path

def config(use_color_logs: bool):
    loger_fname = __get_logs_directory()
    if not os.path.isdir(loger_fname):
        os.mkdir(loger_fname)
    loger_fname = os.path.join(loger_fname, time.strftime("%Y-%m-%d.log"))

    # https://betterstack.com/community/questions/how-to-log-to-file-and-console-in-python/
    # Create a logger
    global __logger
    __logger = logging.getLogger('__logger')
    __logger.setLevel(logging.DEBUG)

    # Create a file handler to write logs to a file
    file_formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S')
    file_handler = logging.FileHandler(loger_fname, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Create a stream handler to print logs to the console
    color_formatter = logging.Formatter(fmt='\033[30m%(asctime)s\033[39m %(levelname)s: %(message)s', datefmt='%H:%M:%S')
    console_formatter = color_formatter if use_color_logs else file_formatter
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)  # You can set the desired log level for console output
    console_handler.setFormatter(console_formatter)

    # Add the handlers to the logger
    __logger.addHandler(file_handler)
    __logger.addHandler(console_handler)

    if use_color_logs:
        # logger config with dimmed time
        # https://docs.python.org/3/howto/logging.html
        # logging.basicConfig(filename=loger_fname,
        #                     format='\033[30m%(asctime)s\033[39m %(levelname)s: %(message)s',
        #                     datefmt='%H:%M:%S',
        #                     level=logging.DEBUG)
        # https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output

        ANSI_FG_WHITE=  "\033[1;37m"
        ANSI_FG_YELLOW= "\033[1;33m"
        ANSI_FG_RED=    "\033[1;31m"
        ANSI_FG_DEFAULT="\033[1;0m"

        # logging.addLevelName(logging.INFO,    "\033[1;37m%s\033[1;0m" % logging.getLevelName(logging.INFO))
        logging.addLevelName(logging.DEBUG,    "DEBUG")
        logging.addLevelName(logging.INFO,    f"{ANSI_FG_WHITE}INFO {ANSI_FG_DEFAULT}")
        logging.addLevelName(logging.WARNING, f"{ANSI_FG_YELLOW}WARN {ANSI_FG_DEFAULT}")
        logging.addLevelName(logging.ERROR,   f"{ANSI_FG_RED}ERROR{ANSI_FG_DEFAULT}")
        logging.addLevelName(logging.FATAL,   f"{ANSI_FG_RED}FATAL{ANSI_FG_DEFAULT}")
    else:
        # logging.basicConfig(filename=loger_fname,
        #                     format='%(asctime)s %(levelname)s: %(message)s',
        #                     datefmt='%H:%M:%S',
        #                     level=logging.DEBUG)

        logging.addLevelName(logging.DEBUG,   "DEBUG")
        logging.addLevelName(logging.INFO,    "INFO ")
        logging.addLevelName(logging.WARNING, "WARN ")
        logging.addLevelName(logging.ERROR,   "ERROR")
        logging.addLevelName(logging.FATAL,   "FATAL")

    __logger.debug("----------------- STARTING -----------------")

# -----------------------------------------------------------------------------

def debug(msg, *args, **kwargs):
    """Log 'msg % args' with severity 'DEBUG'."""
    if __logger is None:
        return
    if __logger.isEnabledFor(logging.DEBUG):
        __logger._log(logging.DEBUG, msg, args, **kwargs)

def info(msg, *args, **kwargs):
    """Log 'msg % args' with severity 'INFO'."""
    if __logger is None:
        return
    if __logger.isEnabledFor(logging.INFO):
        __logger._log(logging.INFO, msg, args, **kwargs)

def warning(msg, *args, **kwargs):
    """Log 'msg % args' with severity 'WARNING'."""
    if __logger is None:
        return
    if __logger.isEnabledFor(logging.WARNING):
        __logger._log(logging.WARNING, msg, args, **kwargs)

def error(msg, *args, **kwargs):
    """Log 'msg % args' with severity 'ERROR'."""
    if __logger is None:
        return
    if __logger.isEnabledFor(logging.ERROR):
        __logger._log(logging.ERROR, msg, args, **kwargs)

def fatal(msg, *args, **kwargs):
    """Don't use this method, use critical() instead."""
    if __logger is None:
        return
    if __logger.isEnabledFor(logging.FATAL):
        __logger._log(logging.FATAL, msg, args, **kwargs)
