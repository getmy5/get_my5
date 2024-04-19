#!/usr/bin/python

import sys
import os
import time
import json
import re

import sqlite3
from sqlite3 import Error
from beaupy import confirm, select, select_multiple
from beaupy.spinners import *
import pyfiglet as PF
from termcolor import colored
from rich.console import Console
from httpx import Client
import jmespath
# import my5getter as my5

#pylint: disable=missing-function-docstring

console = Console()

def create_connection():
    conn = None
    try:
        conn = sqlite3.connect(':memory:')
    except Error as e:
        print(e)
    return conn

def create_database():
    con = create_connection()
    cur = con.cursor()

    sql = '''
    CREATE TABLE IF NOT EXISTS videos(
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    series VARCHAR,
    episode VARCHAR,
    url VARCHAR,
    UNIQUE (url) 
    );
    '''
    cur.execute(sql)
    return con, cur

def keywordsearch(search):
    print("searching", end=' ')
    spinner = Spinner(DOTS)
    spinner.start()  
    client = Client(
        headers={
            'user-agent': 'Dalvik/2.9.8 (Linux; U; Android 9.9.2; ALE-L94 Build/NJHGGF)',
            'Host': 'corona.channel5.com',
            'Origin': 'https://www.channel5.com',
            'Referer':'https://www.channel5.com/',
        }) 

    url = f"https://corona.channel5.com/shows/search.json?platform=my5desktop&friendly=1&query={search}"
    response = client.get(url)
    myjson = response.json()  
    console.print_json(data=myjson)
    res = jmespath.search("""
    shows[].{
    slug: f_name,
    synopsis: s_desc
    } """,  myjson)
    beaupylist = []
    for i in range(0 ,len(res)):
        slug = (res[i]['slug'])
        #title = slug.replace('-', '_').title()
        url =f"https://corona.channel5.com/shows/{slug}/seasons.json?platform=my5desktop&friendly=1"
    
        #url = rinseurl(url)
        synopsis = res[i]['synopsis']
        strtuple = (f"{slug.title()}\t{url}\t{synopsis}")
        beaupylist.append(strtuple)
    spinner.stop()
    found = select(beaupylist)
    return found

def get_next_data(brndslug, url):
    spinner = Spinner(DOTS)
    spinner.start()
    con, cur = create_database()
    # get seasons list
    response = client.get(f"https://corona.channel5.com/shows/{slug}/seasons.json?platform=my5desktop&friendly=1")
    if response.status_code == 200:
        myjson = json.loads(response.content)
    else:
        print (f"Response gave an error {response.status_code} \n {response.content}")
        sys.exit(0)
    console.print_json(data = myjson)

    res = jmespath.search("""
    seasons[*].{
    seasonNumber: seasonNumber,
    sea_f_name: sea_f_name
    } """,  myjson)
    beaupylist = []
    # create list of season urls to get episodes
    # for i in range seasons
    urllist = []
    for i in range(0 ,len(res)):
        if res[i]['seasonNumber'] == None:
            res[i]['seasonNumber'] = '0'
        if  res[i]['sea_f_name'] == None:
            res[i]['sea_f_name'] = "unknown"

        urllist.append(f"https://corona.channel5.com/shows/{slug}/seasons/{res[i]['seasonNumber']}/episodes.json?platform=my5desktop&friendly=1&linear=true")
    allseries = []   
    for url in urllist:
        response = client.get(url)
        if response.status_code == 200:
            myjson = response.json()
            console.print_json(data = myjson)
        else:
            print (f"Response gave an error {response.status_code} \n {response.content}")
            sys.exit(0)
        # odd case has nill results
        # question episodes
        MOVIE = False    
        results = jmespath.search("""
        episodes[*].{
        title: title,
        sea_f_name: sea_f_name,
        f_name: f_name,
        sea_num: sea_num,
        ep_num: ep_num                         
        } """,  myjson)
        if results == []:
            headers = {

                'Accept': 'application/json, text/plain, */*',
                'Host': 'corona.channel5.com',
                'Origin': 'https://www.channel5.com',
                'Referer': 'https://www.channel5.com/',
            }
            url = f"https://corona.channel5.com/shows/{brndslug}/episodes/next.json?platform=my5desktop&friendly=1"
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                myjson = response.json()
                console.print_json(data = myjson)
                results = jmespath.search("""
                    {
                    title: sh_title,
                    sh_f_name: sh_f_name,
                    f_name: f_name,
                    ep_num: ep_num                         
                    } """,  myjson)
                MOVIE = True
            
        totalvideos = 0
        
        
        for i in range (0 , len(results)): #pylint: disable=consider-using-enumerate
            totalvideos += 1
            if not MOVIE:
                url = f"https://www.channel5.com/show/{brndslug}/{results[i]['sea_f_name']}/{results[i]['f_name']}"
                
                sql = f''' INSERT OR IGNORE INTO videos(series, episode, url) VALUES('{results[i]['sea_num']}','{results[i]['ep_num']}','{url}');'''
            else:
                url = f"https://www.channel5.com/show/{results['sh_f_name']}/"
                spinner.stop()
                infoline = "[info] Detected a single Movie; downloading directly\n\n"
                print(colored(infoline, 'green'))
#                 my5.main(url)
                sys.exit(0)
            allseries.append(results[i]['sea_num'])
            cur.execute(sql)
    spinner.stop()
           
    while True:
        if totalvideos <= 16: 
            search = '0'  
            break
        unique_list = list(dict.fromkeys(allseries))
        print("[info] Series found are:-")
        for item in unique_list:
            print(item, end = ' ')
        print("\n[info]There are over 16 videos to display.\nEnter the series number(s) to see a partial list,\n\
        or enter '0' to show all episodes available\n\n\
        Separate series numbers with a space \n")
        search = input("? ")
        if not re.match("^[0-9 ]+$", search):
            print ("Use only numbers and Spaces!")
        else:
            break

    if search == '0':
        cur.execute("SELECT * FROM videos")

    elif type(search) != int:
        srchlist = search.split(' ')
        partsql = "SELECT * FROM videos WHERE series='"
        for srch in srchlist:
            partsql = f"{partsql}{srch}' OR series='"
        partsql = partsql.rstrip(" OR series='")
        sql = partsql + "';"
        cur.execute(sql)

    else:
        search = "Series " + search
        cur.execute("SELECT * FROM videos WHERE series=?", (search,))
    rows = cur.fetchall()
    if len(rows)==0:
        print("[info] No series of that number found. Exiting. Check and try again. ")
    con.close()
    beaupylist = []
    index = [] 
    inx = 0
    for col in rows:
        beaupylist.append(f"{col[1]} {col[2]} {col[3]}")
        index.append(inx)
        inx+=1
    return index, beaupylist


if __name__ == '__main__':
    title = PF.figlet_format(' My5 ', font='smslant')
    print(colored(title, 'green'))
    strapline = "A My5 Video Search, Selector and Downloader.\n\n"
    print(colored(strapline, 'red'))
    client = Client()
    srchurl = ''
    while confirm("Search My5's website on a keyword?\nSelect 'No' to enter a url by hand.\n\n"):
        search = input("Search word(s)?    ")
        if not search:
            print('\nEnter a search term\n')
            continue


        srchurl = keywordsearch(search)
        if srchurl: #
            url = srchurl.split('\t')[1] 
            slug = srchurl.split('\t')[0] 
            print(f"[info] getting data for {slug.title()}")
            break
        else:
            print(f"[info] Nothing found for {search}")

    if not srchurl:
        while True:
            url = input("Enter any My5 url for the series-title to download \n")
            if not url.__contains__('https'):
                print("Enter a correctly formed url \n")
            #if not url.__contains__('show'):
            #    print("\nThat does not appear to be an My5 url. \nTry again.\n")
            else:
                slug = url.split('/')[4]
                break

    index, beaupylist = get_next_data(slug, url)
    dir = "\nUse up/down keys + spacebar to de-select or re-select videos to download\n"
    print(colored(dir, 'red'))
    links = select_multiple(beaupylist, ticked_indices=index,  minimal_count=1, page_size=30, pagination=True)
    for link in links:
        url = link.split(' ')[2]
        print(url)
#        my5.main(url)
    ###############################################################################################
    # The beaupy module that produces checkbox lists seems to clog and confuse my linux box's terminal; 
    # I do a reset after downloading.
    # if that is not what you want, as it may remove any presets, comment out the 'if' phrase below
    # Note: Only resets unix boxes
    ###############################################################################################
    if os.name == 'posix':
        spinner = Spinner(CLOCK, "[info] Preparing to reset Terminal...")
        spinner.start()
        time.sleep(5)
        spinner.stop()     
        os.system('reset')

