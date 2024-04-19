#!/usr/bin/env python

# pylint: disable=consider-using-f-string
# pylint: disable=raise-missing-from
# pylint: disable=line-too-long
# pylint: disable=used-before-assignment
# pylint: disable=invalid-name

'''
    DONE: Allow user to specify Audio type
    DONE: Allow user to specify verbose output, default to quiet
    DONE: Allow user to specify output directory
    DONE: Allow user to specify naming convention to cope with Plex
'''

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import hmac
import hashlib
from urllib.parse import urlparse
from pathlib import Path
import sqlite3
from sqlite3 import Error
import requests

from pywidevine.pssh import PSSH
from pywidevine.device import Device
from pywidevine.cdm import Cdm

from Crypto.Cipher import AES

from config import (
    AES_KEY,
    APP_NAME,
    BASE_URL_MEDIA,
    BASE_URL_SHOWS,
    DEFAULT_HEADERS,
    DEFAULT_JSON_HEADERS,
    DOWNLOAD_DIR,
    HMAC_SECRET,
    TMP_DIR,
    USE_BIN_DIR,
    WVD_PATH,
)

from utility import (
    b64_std_to_url,
    b64_url_to_std,
    delete_temp_files,
    print_with_asterisk,
    safe_name,
)


def generate_episode_url(url: str) -> str | None:
    ''' Generate the episode URL '''
    try:
        if arguments.verbose:
            print("[*] Generating the episode URL...")
        path_segments = urlparse(url).path.strip("/").split("/")

        if path_segments[0] != "show":
            return None

        if len(path_segments) == 2:
            show = path_segments[1]
            return f"{BASE_URL_SHOWS}/{show}/episodes/next.json?platform=my5desktop&friendly=1"
        if len(path_segments) == 4:
            show = path_segments[1]
            season = path_segments[2]
            episode = path_segments[3]
            return f"{BASE_URL_SHOWS}/{show}/seasons/{season}/episodes/{episode}.json?platform=my5desktop&friendly=1&linear=true"
        return None
    except Exception as ex:
        print(f"[!] Exception thrown when attempting to get the episode URL: {ex}")
        raise


def get_content_info(episode_url: str) -> str | None:
    ''' Get the encrypted content info '''
    try:
        if arguments.verbose:
            print("[*] Getting the encrypted content info...")
        r = requests.get(episode_url, headers=DEFAULT_JSON_HEADERS, timeout=10)
        if r.status_code != 200:
            print(
                f"[!] Received status code '{r.status_code}' when attempting to get the content ID"
            )
            return None

        resp = json.loads(r.content)

        if resp["vod_available"] is False:
            return (None, None, None, None, None)

        return (
            resp["id"],
            resp["sea_num"],
            str(resp["ep_num"]),
            resp["sh_title"],
            resp["title"],
        )
    except Exception as ex:
        print(f"[!] Exception thrown when attempting to get the content ID: {ex}")
        raise


def generate_content_url(content_id: str) -> str:
    ''' Generate the content URL '''

    try:
        if arguments.verbose:
            print("[*] Generating the content URL...")
        now = int(time.time() * 1000)
        timestamp = round(now / 1e3)
        c_url = f"{BASE_URL_MEDIA}/{APP_NAME}/{content_id}.json?timestamp={timestamp}"
        sig = hmac.new(base64.b64decode(HMAC_SECRET), c_url.encode(), hashlib.sha256)
        auth = base64.b64encode(sig.digest()).decode()
        return f"{c_url}&auth={b64_std_to_url(auth)}"
    except Exception as ex:
        print(f"[!] Exception thrown when attempting to get the content URL: {ex}")
        raise


def decrypt_content(content: dict) -> str:
    ''' Decrypt the content response '''
    try:
        if arguments.verbose:
            print("[*] Decrypting the content response...")
        key_bytes = base64.b64decode(AES_KEY)
        iv_bytes = base64.b64decode(b64_url_to_std(content["iv"]))
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
        data_bytes = base64.b64decode(b64_url_to_std(content["data"]))
        decrypted_data = cipher.decrypt(data_bytes)
        return decrypted_data[: -decrypted_data[-1]].decode()
    except Exception as ex:
        print(f"[!] Exception thrown when attempting to decrypt the content info: {ex}")
        raise


def get_content_response(content_url: str) -> dict | None:
    ''' Get content response '''

    try:
        if arguments.verbose:
            print("[*] Getting content response...")
        r = requests.get(content_url, headers=DEFAULT_JSON_HEADERS, timeout=10)
        # if code 403 then get new keys
        if r.status_code != 200:
            print(f"[!] Received status code '{r.status_code}' when attempting to get the content response")
            if r.content:
                resp = json.loads(r.content)
                print (f"[!] Failure code: {resp['code']} - {resp['message']}")
            if r.status_code == 403:
                print ("[!] Status 403 means you have to regenerate your keys")
            sys.exit(-1)
        resp = json.loads(r.content)
        return json.loads(decrypt_content(resp))
    except Exception as ex:
        print(f"[!] Exception thrown when attempting to get the content response: {ex}")
        raise


def get_first_rendition(decrypted_content: str) -> None:
    ''' Get First Rendition: Not sure what this does '''
    for asset in decrypted_content["assets"]:
        if asset["drm"] == "widevine":
            if arguments.verbose:
                print_with_asterisk("[LICENSE URL]", asset["keyserver"])

            mpd = urlparse(asset["renditions"][0]["url"])

            mpd_split = mpd.path.split("/")
            mpd_filename = mpd_split[len(mpd_split) - 1]
            stripped_filename = mpd_filename.split("_")[0].split("-")[0]

            default_mpd = mpd.geturl().replace(mpd_filename, f"{stripped_filename}.mpd")
            subtitles_mpd = mpd.geturl().replace(
                mpd_filename, f"{stripped_filename}_subtitles.mpd"
            )

            if arguments.verbose:
                print_with_asterisk("[MPD URL]", default_mpd)
            if arguments.verbose:
                print_with_asterisk("[SUBTITLES URL]", subtitles_mpd)

            return (
                asset["keyserver"],
                default_mpd,
                subtitles_mpd,
            )


def print_decrypted_content(decrypted_content: str):
    ''' Print decrypted content '''
    for asset in decrypted_content["assets"]:
        if asset["drm"] == "widevine":
            print_with_asterisk("[LICENSE URL]", asset["keyserver"])
            print_with_asterisk("[MPD URL]", asset["renditions"][0]["url"])

            for rendition in asset["renditions"]:
                print_with_asterisk("[MPD URL]", rendition["url"])


def get_pssh_from_mpd(mpd: str) -> str | None:
    ''' Extract PSSH from MPD '''
    try:
        if arguments.verbose:
            print_with_asterisk("[*] Extracting PSSH from MPD...")
        r = requests.get(mpd, headers=DEFAULT_JSON_HEADERS, timeout=10)
        if r.status_code != 200:
            print(
                f"[!] Received status code '{r.status_code}' when attempting to get the MPD"
            )
            return None

        return re.findall(r"<cenc:pssh>(.*?)</cenc:pssh>", r.text)[1]
    except Exception as ex:
        print(f"[!] Exception thrown when attempting to get the content ID: {ex}")
        raise


def get_decryption_key(pssh: str, lic_url: str) -> str | None:
    ''' Get decryption keys '''
    cdm = None
    session_id = None
    try:
        if arguments.verbose:
            print("[*] Getting decryption keys...")

        device = Device.load(WVD_PATH)
        cdm = Cdm.from_device(device)
        session_id = cdm.open()
        challenge = cdm.get_license_challenge(session_id, PSSH(pssh))
        r = requests.post(lic_url, data=challenge, headers=DEFAULT_HEADERS, timeout=10)
        if r.status_code != 200:
            print(
                f"[!] Received status code '{r.status_code}' when attempting to get the license challenge"
            )
            return None
        cdm.parse_license(session_id, r.content)

        decryption_key = None
        for key in cdm.get_keys(session_id):
            if key.type == "CONTENT":
                if decryption_key is None:
                    decryption_key = f"{key.kid.hex}:{key.key.hex()}"
                if arguments.verbose:
                    print_with_asterisk("[KEY]", f"{key.kid.hex}:{key.key.hex()}")
        return decryption_key
    except Exception as ex:
        print(f"[!] Exception thrown when attempting to get the decryption keys: {ex}")
        raise
    finally:
        cdm.close(session_id)


def download_streams(mpd: str, show_title: str, episode_title: str) -> str:
    ''' Download streams '''

    try:
        if arguments.verbose:
            print_with_asterisk("[*] Downloading streams...")

        output_title = safe_name(f"{show_title}_{episode_title}")

        yt_dlp = "yt-dlp"
        if USE_BIN_DIR:
            yt_dlp = "./bin/yt-dlp.exe"

        os.makedirs(TMP_DIR, exist_ok=True)

        # It's at this point that we want to allow the selection of normal audio (wa) or
        # include the audio description
        # DONE: Allow user to select audio quality

        if arguments.audio_description:
            video_audio = "bv,ba"
        else:
            video_audio = "bv,wa"

        # TODO: Disable progress bar
        args = [
            yt_dlp,
            "--allow-unplayable-formats",
            "-q",
            "--no-warnings",
            "--progress",
            "-f",
            video_audio,
            mpd,
            "-o",
            f"{TMP_DIR}/encrypted_{output_title}.%(ext)s",
        ]
        subprocess.run(args, check=True)
        return output_title
    except KeyboardInterrupt:
        print ("Shutdown requested...exiting")
        delete_temp_files()
        sys.exit(130)
    except Exception as ex:
        print(f"[!] Exception thrown when attempting to download streams: {ex}")
        raise


def decrypt_streams(decryption_key: str, output_title: str) -> list:
    ''' Decrypt streams '''
    try:
        if arguments.verbose:
            print("[*] Decrypting streams...")

        mp4_decrypt = "mp4decrypt"
        if USE_BIN_DIR:
            mp4_decrypt = "./bin/mp4decrypt.exe"

        files = []
        for file in os.listdir(TMP_DIR):
            if output_title in file:
                encrypted_file = f"{TMP_DIR}/{file}"
                file = file.replace("encrypted_", "decrypted_")
                output_file = f"{TMP_DIR}/{file}"
                files.append(output_file)
                args = [
                    mp4_decrypt,
                    "--key",
                    decryption_key,
                    encrypted_file,
                    output_file,
                ]
                subprocess.run(args, check=True)

        for file in os.listdir(TMP_DIR):
            if "encrypted_" in file:
                os.remove(f"{TMP_DIR}/{file}")
        return files
    except KeyboardInterrupt:
        print ("Shutdown requested...exiting")
        delete_temp_files()
        sys.exit(130)

    except Exception as ex:
        print(f"[!] Exception thrown when attempting to decrypt the streams: {ex}")
        raise


def get_output_file_name (show_title, season_number, episode_number, episode_title) -> str:
    ''' Return the base output file name '''
    date_regex = r"(monday|tuesday|wednesday|thursday|friday) \d{0,2} (january|february|march|april|may|june|july|august|september|october|november|december)"
    if re.match(date_regex, episode_title, re.I):
        episode_title = ""

    # TODO: Should probably change this to f"{x:02d}"
    if season_number is None:
        season_number = "01"
    if len(season_number) == 1:
        season_number = f"0{season_number}"
    if len(episode_number) == 1:
        episode_number = f"0{episode_number}"

    if "Episode " in episode_title:
        if len(show_title.split(":")) == 2:
            episode_title = show_title.split(":")[1]
        else:
            episode_title = ""

    if len(episode_title.split(":")) == 2:
        episode_title = episode_title.split(":")[1]

    if show_title == episode_title or (
        len(show_title.split(":")) == 2
        and show_title.split(":")[1] in episode_title
    ):
        episode_title = ""

    # added line to specify creating the output dir with a Season XX bit
    if arguments.plex:
        output_dir = f"{DOWNLOAD_DIR}/{safe_name(show_title)}/Season {season_number}"
    else:
        output_dir = f"{DOWNLOAD_DIR}/{safe_name(show_title)}"

    season_number = f"S{season_number}"
    episode_number = f"E{episode_number}"

    output_file = output_dir + " ".join(
        f"/{safe_name(show_title)} {season_number}{episode_number} {episode_title}".split()
    ).replace(" ", ".")

    return output_dir, output_file


def merge_streams(
    files: list,
    show_title: str,
    season_number: str,
    episode_number: str,
    episode_title: str,
    subtitles_url: str,
    dl_subtitles: bool,
):
    ''' Merge streams '''
    try:
        if arguments.verbose:
            print("[*] Merging streams...")

        # DONE: This section needs to be updated to allow for change to output dir and naming convention

        (output_dir, output_file) = get_output_file_name (show_title, season_number, episode_number, episode_title)

        ffmpeg = "ffmpeg"
        if USE_BIN_DIR:
            ffmpeg = "./bin/ffmpeg.exe"

        os.makedirs(output_dir, exist_ok=True)

        args = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            files[0],
            "-i",
            files[1],
            "-c",
            "copy",
            f"{output_file}.mp4",
        ]
        if arguments.force:
            args.insert(1, '-y')

        subprocess.run(args, check=True)

        if dl_subtitles:
            try:
                if arguments.verbose:
                    print("[*] Downloading subtitles...")
                resp = requests.get(subtitles_url, DEFAULT_HEADERS, timeout=10)
                if resp.status_code != 200:
                    if arguments.verbose:
                        print("[*] Subtitles are not available")
                    return

                with open(f"{output_file}.vtt", mode="wb") as file:
                    file.write(resp.content)
            except Exception as ex:
                print(
                    f"[!] Exception thrown when attempting to download subtitles: {ex}"
                )
                raise
    except:
        print("[!] Failed merging streams")
        raise


def check_required_config_values() -> None:
    ''' Check that the required config parameters are present'''

    lets_go = True
    if not HMAC_SECRET:
        print("[*] HMAC_SECRET not set")
        lets_go = False
    if not AES_KEY:
        print("[*] AES_KEY not set")
        lets_go = False
    if not WVD_PATH:
        print("[*] WVD_PATH not set")
        lets_go = False
    if WVD_PATH and not os.path.exists(WVD_PATH):
        print("[*] WVD file does not exist")
    if not lets_go:
        sys.exit(1)


def get_episode (url: str) -> None:
    ''' Get a particular episode'''

    # Generate the episode URL
    episode_url = generate_episode_url(url)
    if episode_url is None:
        print("[!] Failed to get the episode URL")
        sys.exit(1)

    # Get the C5 content ID by parsing the response of the episode URL
    (
        content_id,
        season_number,
        episode_number,
        show_title,
        episode_title,
    ) = get_content_info(episode_url)
    if content_id is None:
        print(f"[!] Episode is not available ({url})")
        return

    # We now have the show info, does the ultimate output file exist?

    # Generate the content URL from the C5 content ID
    content_url = generate_content_url(content_id)

    # Get the decrypted content response
    content_response = get_content_response(content_url)

    # Get the WVD key server URL, MPD and WebVTT from the first rendition
    lic_url, mpd_url, subtitles_url = get_first_rendition(content_response)

    # Get the MPD and extract the PSSH
    pssh = get_pssh_from_mpd(mpd_url)

    # Decrypt
    decryption_key = get_decryption_key(pssh, lic_url)

    if arguments.download:
        delete_temp_files()
        (_, output_file) = get_output_file_name (show_title, season_number, episode_number, episode_title)

        if Path(f"{output_file}.mp4").is_file() and not arguments.force:
            print (f"{output_file}.mp4 already exists. Use --force to overwrite")
            return

        output_title = download_streams(mpd_url, show_title, episode_title)
        decrypted_file_names = decrypt_streams(decryption_key, output_title)
        merge_streams(
            decrypted_file_names,
            show_title,
            season_number,
            episode_number,
            episode_title,
            subtitles_url,
            arguments.subtitles,
        )
        delete_temp_files()

    if arguments.verbose:
        print("[*] Done")


def create_connection() -> sqlite3.Connection:
    ''' Connect to database.
        If a database name is provided then attempt to connect to it
        If the --create flag has been passed then explicitly create a new DB 
        or zero out (by deletion) an existing one.

        If no db name has been provided and the --create option isn't given, try
        to create a new DB in the usual places.
    '''
    con = None
    if arguments.db:
        try:
            cache_db = Path(arguments.db)
            if not cache_db.is_file():
                print (f"{cache_db} does not exist, please create it")
                sys.exit(-1)

            con = sqlite3.connect(cache_db)
        except sqlite3.Error as error:
            print("Failed to connect to sqlite database", error)
            sys.exit()
        except Error as e:
            print(f"{e} DB File is {cache_db}")
            sys.exit()
        return con

    home_dir = Path.home()
    cache_db = home_dir / ".config" / "get_my5" / "cache.db"
    if not cache_db.is_file():
        print (f"Default DB, {cache_db}, does not exist, please create it")
        sys.exit(-1)

    try:
        return sqlite3.connect(cache_db)
    except PermissionError:
        print (f"You don't have permission to create the directory {cache_db.parent}")
        sys.exit(-1)
    except Error as e:
        print(f"{e} - DB File is {cache_db}")
        sys.exit(-1)


def get_episode_url (show: str, season: str, episode: list) -> list:

    ''' Find the episode in the cache '''

    # x = f"SELECT * FROM distro WHERE id IN (%s)" % ("?," * len(a))[:-1]
    url = []

    sql = '''
select
    episodes.season_number, episode_name, episode_number, episode_url
from episodes
inner join shows on shows.id = episodes.id
where 
    shows.id = episodes.id and 
    shows.title = ? and 
    episodes.season_number = ? and 
    episode_number in (%s)
''' % ("?," * len(episode))[:-1]
    con = None
    try:
        con = create_connection()
        if not con:
            sys.exit(-1)
        cur = con.cursor()
        cur.execute(sql, (show, season, *episode))
        rows = cur.fetchall()
        con.close()
        found = []
        if rows: # found
            for r in rows: # found
                found.append(r[2])
                if arguments.verbose:
                    print (f"Found {r[3]}")
                url.append(r[3])
        else:
            for i in episode:
                print (f"Can't find Episode {i} of {show}, Season {season}")
            sys.exit(-1)
    except sqlite3.Error as error:
        print("Failed to read data from sqlite table", error)
    finally:
        if con:
            con.close()

    s = set(found)
    not_found = [x for x in episode if x not in s]
    for i in not_found:
        print (f"Can't find Episodes {i} of {show}, Season {season}")

    return url


def get_season_url (show: str, season: str) -> list:

    ''' Find the episode in the cache '''
    url = []

    sql = '''
select
    episodes.season_number, episode_name, episode_number, episode_url
from episodes
inner join shows on shows.id = episodes.id
where 
    shows.id = episodes.id and 
    shows.title = ? and 
    episodes.season_number = ?
'''
    con = None
    try:
        con = create_connection()
        if not con:
            sys.exit(-1)
        cur = con.cursor()
        cur.execute(sql, (show, season))
        rows = cur.fetchall()
        cur.close()
        if rows:
            for r in rows: # found
                if arguments.verbose:
                    print (f"Found {r[3]}")
                url.append(r[3])
        else:
            print (f"Can't find Season {season} of {show}")
            sys.exit(-1)
    except sqlite3.Error as error:
        print("Failed to read data from sqlite table", error)
    finally:
        if con:
            con.close()
    return url


def search_show (show: str) -> list:

    ''' Find the episode in the cache '''
    url = []

    show_sql = '''
select
    id, title
from 
    shows
where 
    shows.title like ?
'''
    seasons_sql = '''
select
    *
from 
    seasons
where 
    id = ?
'''
    episodes_sql = '''
select
    *
from 
    episodes
where 
    id = ?
'''

    con = None
    try:
        con = create_connection()
        if not con:
            sys.exit(-1)
        cur = con.cursor()
        cur.execute(show_sql, (f"%{show}%",))
        rows = cur.fetchall()
        if rows:
            for r in rows: # found
                cur.execute(seasons_sql, (r[0], ))
                seasons = cur.fetchall()
                cur.execute(episodes_sql, (r[0], ))
                # episodes = cur.fetchall()[0][0]
                episodes = cur.fetchall()
                if len(seasons) == 0:
                    print (f"Found {r[1]} (One Off)")
                else:
                    print (f"Found {r[1]} with {len(seasons)} Seasons and {len(episodes)} Episodes")
                    if arguments.list:
                        for s in seasons:
                            print (f"Season {s[2]:02d} ({s[3]}):")
                            for e in episodes:
                                if e[3] == s[2]:
                                    print (f"\tS{s[2]:02d}E{e[5]:02d} - {e[2]}")

        else:
            print (f"Can't find a match for {show}")
        cur.close()
    except sqlite3.Error as error:
        print("Failed to read data from sqlite table", error)
    finally:
        if con:
            con.close()
    return url


def get_show_url (show: str) -> list:

    ''' Find the episode in the cache '''
    url = []

    sql = '''
select
    episodes.season_number, episode_name, episode_number, episode_url
from episodes
inner join shows on shows.id = episodes.id
where 
    shows.id = episodes.id and 
    shows.title = ?
'''
    con = None
    try:
        con = create_connection()
        if not con:
            sys.exit(-1)
        cur = con.cursor()
        cur.execute(sql, (show,))
        rows = cur.fetchall()
        cur.close()
        if rows:
            for r in rows: # found
                if arguments.verbose:
                    print (f"Found {r[3]}")
                url.append(r[3])
        else:
            print (f"Can't find ay episodes for {show}")
            sys.exit(-1)
    except sqlite3.Error as error:
        print("Failed to read data from sqlite table", error)
    finally:
        if con:
            con.close()
    return url


def create_argument_parser():
    ''' Process the command line arguments '''

    def list_of_ints(arg):
        return list(map(int, arg.split(',')))

    parser = argparse.ArgumentParser(description="Channel 5 downloader.")

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument("--url",     help="The URL of the episode to download")
    group.add_argument("--search",  help="Name of show to search for")
    group.add_argument("--show",    help="Name of show to download")

    group_episode = parser.add_mutually_exclusive_group()
    group_episode.add_argument("--episode", type=list_of_ints, help="Episode(s) wanted")

    group_season = parser.add_mutually_exclusive_group()
    group_season.add_argument("--season",  help="Season wanted")
    group_season.add_argument('--season-list', type=list_of_ints, help="List of Seasons wanted (TODO)")

    parser.add_argument("--db",      help="Path to database")

    parser.add_argument("--download", "-d", help="Flag to download the episode", action="store_true")
    parser.add_argument("--subtitles", "-s", help="Flag to download subtitles", action="store_true")
    parser.add_argument("--audio-description", "-ad", help="Download Audio Description audio track", action="store_true")

    parser.add_argument("--verbose", "-v", help="Verbose output", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Don't do anything, just print out proposed actions (TODO)")
    parser.add_argument("--plex", help="Include Season in output dir", action="store_true")
    parser.add_argument("--force", help="Force overwrite of output file", action="store_true")
    parser.add_argument("--list", help="List the episodes available from search", action="store_true")

    args = parser.parse_args()

    if args.list and not args.search:
        print ("--list only available with --search")
        sys.exit(-1)

    if args.episode and not args.season:
        print ("A season must be specified if the --episode or --episode-list is given")
        sys.exit(-1)

    return args


def main() -> None:
    '''
        Programme to download content from Channel 5 in the UK (my5.tv)
        Cloned and extensively modified from the original https://github.com/Diazole/my5-dl
    '''
    if arguments.search:
        search_show (arguments.search)
        return

    fetch_url = []
    if arguments.show:
        if arguments.episode: # we want a single episode (we know the season)
            fetch_url = get_episode_url(arguments.show, arguments.season, arguments.episode)
        else:
            if arguments.season and not arguments.episode: # we want a whole season
                fetch_url = get_season_url(arguments.show, arguments.season)
            else:
                fetch_url = get_show_url(arguments.show)
    else:
        fetch_url.append(arguments.url)

    for url in fetch_url:
        if arguments.verbose:
            print (f"Get {url}")
        get_episode (url)


if __name__ == "__main__":

    # We need to check the arguments supplied before anything else.

    arguments = create_argument_parser()
    check_required_config_values()

    main()
