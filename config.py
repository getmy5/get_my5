''' This file contains configuration options '''
# pylint: disable=line-too-long
import sys

from pathlib import Path
from decouple import config, RepositoryEnv, Config

def get_env_file() -> str | None:
    '''
    Get's the location of the env file for rhe project
    Looks for
        $HOME/.config/get_my5/.env
        $HOME/.get_my5/.env
        ./.env

    As we use pathlib the function is compatible with windows.

    '''

    home_dir = Path.home()

    # first check for $HOME/.config/get_my5/.env
    env_file_name = home_dir / ".config" / "get_my5" / ".env"
    if env_file_name.is_file():
        return env_file_name

    env_file_name = home_dir / ".get_my5" / ".env"
    if env_file_name.is_file():
        return env_file_name

    app_dir_path = Path(__file__).resolve().parent
    env_file_name = app_dir_path / ".env"
    if env_file_name.is_file():
        return env_file_name

    # No .env file has been found
    print ("Environment file not found")
    sys.exit(1)


config = Config(RepositoryEnv(get_env_file()))

# Configurable

HMAC_SECRET = config('HMAC_SECRET', default="")
AES_KEY = config('AES_KEY', default="")
WVD_PATH = config('WVD_PATH', default="")

DOWNLOAD_DIR = config('DOWNLOAD_DIR', default="./downloads")
TMP_DIR = config('TMP_DIR', default="./tmp")
BIN_DIR = config('BIN_DIR', default="./bin")
USE_BIN_DIR = config('USE_BIN_DIR', default=False, cast=bool)

# Don't touch
APP_NAME = "my5desktopng"
BASE_URL_MEDIA = "https://cassie.channel5.com/api/v2/media"
BASE_URL_SHOWS = "https://corona.channel5.com/shows"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
DEFAULT_HEADERS = {
    "Accept": "*/*",
    "User-Agent": USER_AGENT,
}
DEFAULT_JSON_HEADERS = {
    "Content-type": "application/json",
    "Accept": "*/*",
    "User-Agent": USER_AGENT,
}
