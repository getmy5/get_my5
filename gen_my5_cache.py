#!/usr/bin/python

#pylint: disable=missing-function-docstring, missing-module-docstring, line-too-long, missing-class-docstring, used-before-assignment

import sys
import sqlite3
from sqlite3 import Error
import argparse
from pathlib import Path

from httpx import Client

import jmespath

class Show:
    def __init__(self, title: str, url: str, alt_title: str):
        self.title = title
        self.url = url
        self.alt_title = alt_title

def create_connection() -> sqlite3.Connection:
    ''' Connect to database.
        If a database name is provided then attempt to connect to it
        If the --create flag has been passed then explicitly create a new DB
        or zero out (by deletion) an existing one.

        If no db name has been provided and the --create option isn't given, try
        to create a new DB in the usual places.
    '''
    if args.db:
        try:
            cache_db = Path(args.db)
            if not cache_db.is_file() and not args.create:
                print (f"{cache_db} does not exist, use --create to create it")
                sys.exit(-1)

            if cache_db.is_file() and args.create:
                cache_db.unlink()
            return sqlite3.connect(cache_db)
        except Error as error:
            print(f"{error} DB File is {cache_db}")
            sys.exit()

    home_dir = Path.home()
    cache_db = home_dir / ".config" / "get_my5" / "cache.db"
    if not cache_db.is_file() and not args.create:
        print (f"Default DB, {cache_db}, does not exist, use --create to create it")
        sys.exit(-1)

    try:
        cache_db.parent.mkdir(parents=True, exist_ok=True)
        if args.create:
            cache_db.unlink()

        return sqlite3.connect(cache_db)
    except PermissionError:
        print (f"You don't have permission to create the directory {cache_db.parent}")
        sys.exit(-1)
    except Error as error:
        print(f"{error} - DB File is {cache_db}")
        sys.exit(-1)

def create_database(con: sqlite3.Connection) -> sqlite3.Cursor:

    cur = con.cursor()

    sql = '''
    CREATE TABLE IF NOT EXISTS shows(
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        id INT,
        title VARCHAR,
        alt_title VARCHAR,
        genre VARCHAR,
        sub_genre VARCHAR,
        synopsis VARCHAR,
        UNIQUE(id)
    );
    '''
    cur.execute(sql)
    sql = '''
    CREATE TABLE IF NOT EXISTS seasons(
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        id INT,
        season_number INT,
        season_name VARCHAR,
        numberOfEpisodes INT,
        UNIQUE(id, season_number)
    );
    '''
    cur.execute(sql)
    sql = '''
    CREATE TABLE IF NOT EXISTS episodes(
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        id INT,
        title VARCHAR,
        season_number INT,
        episode_name VARCHAR,
        episode_number INT,
        episode_description VARCHAR,
        episode_url VARCHAR,
        episode_id VARCHAR,
        UNIQUE(episode_number, episode_url)
    );
    '''
    cur.execute(sql)
    return cur

def get_all_shows(con: sqlite3.Connection) -> None:
    ''' Perform a keyword search on the Channel 5 site '''

    cur = create_database(con)

    client = Client(
        headers={
            'user-agent': 'Dalvik/2.9.8 (Linux; U; Android 9.9.2; ALE-L94 Build/NJHGGF)',
            'Host': 'corona.channel5.com',
            'Origin': 'https://www.channel5.com',
            'Referer':'https://www.channel5.com/',
        })

    url = "https://corona.channel5.com/shows/search.json?platform=my5desktop&friendly=1"
    try:
        response = client.get(url, timeout=30)
    except KeyboardInterrupt:
        print ("Interrupted - No data committed")
        sys.exit(-1)

    myjson = response.json()

    show_data = jmespath.search("""
                            shows[].{
                                id: id,
                                title: title,
                                alt_title: f_name,
                                synopsis: s_desc,
                                genre: genre,
                                sub_genre: primary_vod_genre
                            }
                          """,  myjson)

    for _, show in enumerate(show_data):
        sql = '''INSERT OR IGNORE INTO
                    shows (id, title, alt_title, genre, sub_genre, synopsis)
               VALUES (?, ?, ?, ?, ?, ?)'''
        # We can assume that if the cache is being built then all shows are new. Otherwise
        # print that we have a new show
        if not args.create:
            query = "SELECT ? from shows where id = ?"
            try:
                cur.execute(query, (show['id'], show['id'], ))
            except sqlite3.Error as error:
                print("Failed to connect to sqlite database", error)
                sys.exit()
            rows = cur.fetchall()
            if not rows: # New Show
                print (f"Found new show: {show['title']}")
        else:
            print (f"Found show: {show['title']}")

        try:
            cur.execute(sql, (
                    show['id'],
                    show['title'],
                    show['alt_title'],
                    show['genre'],
                    show['sub_genre'],
                    show['synopsis'], ))
        except sqlite3.Error as error:
            print("Failed to connect to sqlite database", error)
            sys.exit()

        get_seasons(cur, client, show)

    con.commit()
    con.close()

def get_seasons(cur: sqlite3.Cursor, client, show) -> None:

    url =f"https://corona.channel5.com/shows/{show['alt_title']}/seasons.json?platform=my5desktop&friendly=1"
    try:
        response = client.get(url, timeout=30)
    except KeyboardInterrupt:
        print ("Interrupted - No data committed")
        sys.exit(-1)
    myjson = response.json()

    season_data = jmespath.search("""
                        seasons[].{
                            season_number: seasonNumber,
                            season_name: sea_f_name,
                            numberOfEpisodes: numberOfEpisodes
                        }
                        """,  myjson)
    for _, season in enumerate(season_data):
        if season['season_number']:
            query = "SELECT id, season_number, numberOfEpisodes from seasons where id = ? and season_number= ?"
            try:
                cur.execute(query, (show['id'], season['season_number'], ))
            except sqlite3.Error as error:
                print("Failed to connect to sqlite database", error)
                sys.exit()
            rows = cur.fetchall()
            if not rows:
                print(f"New season for {show['title']}, Season {season['season_number']}")
                sql = '''INSERT OR IGNORE INTO seasons(id, season_number, season_name, numberOfEpisodes) VALUES (?, ?, ?, ?)'''
                try:
                    cur.execute(sql, (show['id'], season['season_number'], season['season_name'], season['numberOfEpisodes'], ))
                except sqlite3.Error as error:
                    print("Failed to connect to sqlite database", error)
                    sys.exit()
                # TODO: We need to check if a season has been removed.
            else:
                if season['numberOfEpisodes'] > rows[0][2]:
                    print(f"Found extra episodes of {show['title']}, Season {season['season_number']} was {rows[0][2]} now {season['numberOfEpisodes']}")
                if season['numberOfEpisodes'] < rows[0][2]:
                    print(f"Episodes removed from {show['title']}, Season {season['season_number']} was {rows[0][2]} now {season['numberOfEpisodes']}")
                sql = '''UPDATE seasons SET numberOfEpisodes = ? WHERE id = ? and season_number = ?'''
                try:
                    cur.execute(sql, (season['numberOfEpisodes'], show['id'], season['season_number'], ))
                except sqlite3.Error as error:
                    print("Failed to connect to sqlite database", error)
                    sys.exit()

            get_episodes(cur, client, show, season)
        else:
            get_one_off(cur, show)

def get_one_off (cur, show) -> None:

    url = f"https://www.channel5.com/show/{show['alt_title']}"
    if not show['synopsis']:
        show['synopsis'] = "None"

    sql = "INSERT OR IGNORE INTO episodes (id, title, episode_description, episode_url) VALUES (?, ?, ?, ?)"
    try:
        cur.execute(sql, (show['id'], show['title'], show['synopsis'], url, ))
    except sqlite3.Error as error:
        print("Failed to connect to sqlite database", error)
        sys.exit()

def get_episodes (cur: sqlite3.Cursor, client, show, season) -> None:

    episode_url = f"https://corona.channel5.com/shows/{show['alt_title']}/seasons/{season['season_number']}/episodes.json?platform=my5desktop&friendly=1&linear=true"

    try:
        response = client.get(episode_url, timeout=30)
    except KeyboardInterrupt:
        print ("Interrupted")
        sys.exit(-1)

    myjson = response.json()
    results = jmespath.search("""
                    episodes[*].{
                    title: title,
                    episode_name: f_name,
                    ep_num: ep_num,
                    ep_description: s_desc,
                    ep_id: id
                    } """,  myjson)
    for _, value in enumerate(results):
        # TODO: Need to figure out if an episode has been deleted.
        # This has sort of been taken care of by making an attempt to download a deleted episode
        # a non-fatal error.
        query = "SELECT season_number, episode_number FROM episodes WHERE season_number=? and episode_number=? and id=?"
        try:
            cur.execute(query, (season['season_number'], value['ep_num'], show['id'], ))
        except sqlite3.Error as error:
            print("Failed to connect to sqlite database", error)
            sys.exit()
        rows = cur.fetchall()
        if not rows:
            print (f"Found new episode for {show['title']}, Season {season['season_number']}, Episode {value['ep_num']} - {value['ep_description']}")

        url = f"https://www.channel5.com/show/{show['alt_title']}/{season['season_name']}/{value['episode_name']}"
        sql = '''INSERT OR IGNORE INTO
                    episodes (id, title, season_number, episode_name, episode_number, episode_description, episode_url, episode_id)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               '''
        try:
            cur.execute(sql, (
                show['id'],
                value['title'],
                season['season_number'],
                value['episode_name'],
                value['ep_num'],
                value['ep_description'],
                url,
                value['ep_id'], ))
        except sqlite3.Error as error:
            print("Failed to connect to sqlite database", error)
            sys.exit()

def arg_parser():

    ''' Process the command line arguments '''

    parser = argparse.ArgumentParser(description="Channel 5 Cache Builder.")
    parser.add_argument(
        "--db",
        help="Database name"
    )
    parser.add_argument(
        "--create",
        help="Create a new cache database",
        default=False,
        action="store_true",
    )


    return parser.parse_args()

def main() -> None:

    con = create_connection()

    get_all_shows(con)

    sys.exit(0)

if __name__ == '__main__':

    args = arg_parser()

    main()
