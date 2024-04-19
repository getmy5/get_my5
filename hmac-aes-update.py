#!/usr/bin/python
'''
    # Based on the original script by A_n_g_e_l_a
    # this script runs a headless version of firefox to run Diazole's retrieve-keys.html,
    # local - on your system.
    # it then updates the .env file
    # You will need a firefox binary file - geckodriver - see here to download
    # https://github.com/mozilla/geckodriver/releases
    # pip install selenium   - if you haven't used selenium before

'''
#pylint: disable=invalid-name
#pylint: disable=line-too-long

import time
import json
import argparse
import sys

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import WebDriverException

def replace_key(file_name, key, text) -> None:
    '''
        The problem with this routine was that it assumes that the HMAC_SECRET and AES_KEY
        are in set positions in the .env file. 

        Modifications required to fix this.
     
    '''
    try:
        with open(file_name, 'r', encoding="utf-8") as env_file:
            lines = env_file.readlines()
    except FileNotFoundError:
        print(f"Environment file {file_name} does not exist")
        sys.exit(-1)
    except PermissionError:
        print(f"You do not have permission to open environment file {file_name}")
        sys.exit(-1)

    for i, line in enumerate(lines):
        y = [item.strip() for item in line.split('=', 1)]
        if y[0] == key:
            lines[i] = f'{key} = "{text}"\n'

    with open(file_name, 'w+', encoding="utf-8") as env_file:
        env_file.writelines(lines)
        env_file.close()

def get_keys(key_file: str) -> dict:
    '''
        Call headless firefox to run page and get values returned
        TODO: Add more error handling
    '''
    options = Options()
    options.add_argument('-headless')

    driver = webdriver.Firefox(options=options)
    try:
        driver.get(key_file)
    except WebDriverException:
        print (f"Cannot load {key_file}")
        sys.exit(-1)

    time.sleep(3) # do not remove this! Edit seconds to wait up if you get 'None' reported.
    source = driver.page_source
    driver.close()

    result = source.replace('<html><head></head><body>','').replace('</body></html>','')
    return json.loads(result)

def argument_parser():
    ''' Process the command line arguments '''

    parser = argparse.ArgumentParser(description="Channel 5 downloader. Key updater")
    parser.add_argument("--env", help = "Name of .env file", required = True)
    parser.add_argument("--keys", help = "Name of retrieve-keys file", required = True)

    args = parser.parse_args()

    if not args.env:
        parser.print_help()
        sys.exit(1)
    return args

def main() -> None:
    '''
        MAIN
    '''
    arguments = argument_parser()

    mydict = get_keys(arguments.keys)

    # replace_line(<path to your file> , <key>, <text>)
    replace_key(arguments.env, "HMAC_SECRET", mydict['HMAC_SECRET'])
    replace_key(arguments.env, "AES_KEY", mydict['AES_KEY'])

if __name__ == "__main__":

    main()
