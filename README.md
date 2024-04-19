# Channel 5 (My5) Downloader

An AIO python script to download Channel 5 (My5) content.

## Requirements

* Python 3.6.*
* pip
* ffmpeg (<https://github.com/FFmpeg/FFmpeg>)
* mp4decrypt (<https://github.com/axiomatic-systems/Bento4>)
* yt-dlp (<https://github.com/yt-dlp/yt-dlp>)
* WVD file (<https://github.com/rlaphoenix/pywidevine>)

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
usage: get_my5.py [-h] (--url URL | --search SEARCH | --show SHOW) 
                [--episode EPISODE | --episode-list EPISODE_LIST]
                [--season SEASON | --season-list SEASON_LIST] [--db DB]
                [--download] [--subtitles] [--audio-description] [--verbose]
                [--dry-run] [--plex] [--list]
                [--force]
```

### Arguments

```bash
  --help, -h            show this help message and exit
  --url URL             The URL of the episode to download
  --search SEARCH       Name of show to search for
  --show SHOW           Name of show to download
  --episode EPISODE     Episode(s) wanted
  --season SEASON       Season wanted
  --season-list SEASON_LIST
                        List of Seasons wanted (TODO)
  --db DB               Path to database
  --download, -d        Flag to download the episode
  --subtitles, -s       Flag to download subtitles
  --audio-description, -ad
                        Download Audio Description audio track
  --verbose, -v         Verbose output
  --dry-run             Don't do anything, just print out proposed actions (TODO)
  --plex                Include Season in output dir
  --force               force overwrite of output file
  --list                List the episodes available from search

```

### Example usage

```bash
./get_my5.py --show "My Show" --season 1 --episode 1,2,3 --plex --download
./get_my5.py --search "Show" --list
./get_my5.py --url https://www.channel5.com/show/wanted-show --plex --download
```

## Config

Config is located in `config.py`

`HMAC_SECRET` - HMAC secret used to generate the authentication key for the
                content URL  
`AES_KEY` -     AES key used to decrypt the data field of the API response  
`BIN_DIR` -     Path to where your binaries installed  
`USE_BIN_DIR` - Flag indicating whether to use the binaries in the BIN_DIR
                path or your system/user path  
`DOWNLOAD_DIR` - Path to your download directory  
`TMP_DIR` -     Path to your temp directory  
`WVD_PATH` -    Path to your WVD file

All the above config variables can be overridden by creating a `.env` file,
a `settings.ini` file. This is recommended for `HMAC_SECRET` and `AES_KEY`
to prevent Git warnings. The programme looks in:
        $HOME/.config/get_my5/.env
        $HOME/.get_my5/.env
        ./.env

As we use pathlib, the function is compatible with windows.

In Linux it is also possible to override the values by specifying the value on the
command line.

See <https://pypi.org/project/python-decouple/> for full details.

## Retrieving Keys

The `HMAC_SECRET` and `AES_KEY` keys can be retrieved by opening
`./keys/retrieve-keys.html` in your browser.

The application hmac-aes-update.py can be used to automatically update these values:

### Example usage

```bash
./hmac-aes-update.py --env .env --keys file://$HOME/src/get_my5/keys/retrieve-keys.html
```

## Cache Generation

### Usage

```bash
./gen_cache.py [-h] [--db DB] [--create]

```

### Arguments

```bash
--db   Alternative DB file name (Defaults to $HOME/.config/.get_m5/cache.db).
--create  Explicit create needed if file does not exist.
```

## Disclaimer

1. This script requires a Widevine RSA key pair to retrieve the decryption key
   from the license server.
2. This script is purely for educational purposes and should not be used to
   bypass DRM protected content.
