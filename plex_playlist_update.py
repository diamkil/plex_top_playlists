#!/usr/bin/env python

# a python test script
# -*- coding: utf-8 -*-

#------------------------------------------------------------------------------
#
#         Automated Ranked Playlists - RugbyHunter231
#
#                         *** Use at your own risk! ***
#   *** I am not responsible for damages to your Plex server or libraries. ***
#
#------------------------------------------------------------------------------

import time
import re
import json
import os
import requests
import subprocess
import time
import xmltodict
import configparser
from lxml.html import parse
from plexapi.server import PlexServer
import lxml
from urllib.request import urlopen
#from plexapi.utils import NA
NA=""

config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'settings.ini')
config = configparser.SafeConfigParser()
config.read(config_file_path)

PLEX_URL = os.environ['HOST']
PLEX_TOKEN = os.environ['TOKEN']
MOVIE_LIBRARY_NAME = os.environ['MOVIES']
SHOW_LIBRARY_NAME = os.environ['TV']
REMOVE_ONLY = False
SYNC_WITH_SHARED_USERS = True
try:
    PLEX_TIMEOUT = 300
except:
    PLEX_TIMEOUT = 300
TRAKT_API_KEY = os.environ['TRAKT_API']
TRAKT_NUM_MOVIES = os.environ['TRAKT_TOTAL_MOVIE']
TRAKT_WEEKLY_PLAYLIST_NAME = os.environ['WEEKLY_MOVIE_NAME']
TRAKT_POPULAR_PLAYLIST_NAME = os.environ['POPULAR_MOVIE_NAME']
TRAKT_NUM_SHOWS = os.environ['TRAKT_TOTAL_TV']
TRAKT_WEEKLY_SHOW_PLAYLIST_NAME = os.environ['WEEKLY_TV_NAME']
TRAKT_POPULAR_SHOW_PLAYLIST_NAME = os.environ['POPULAR_TV_NAME']
# these are the new lists
IMDB_SEARCH_LISTS = json.loads(config.get('IMDb', 'search-lists'))
IMDB_CHART_LISTS = json.loads(config.get('IMDb', 'chart-lists'))
START_TIME = time.time()

####### CODE HERE (Nothing to change) ############

def log_timer(marker = ""):
    print (">>> {0} seconds {1}".format(
        time.time() - START_TIME,
        marker
    ))

def get_user_tokens(server_id):
    headers = {'Accept': 'application/json', 'X-Plex-Token': PLEX_TOKEN}
    result = requests.get('https://plex.tv/api/servers/{server_id}/shared_servers?X-Plex-Token={token}'.format(server_id=server_id, token=PLEX_TOKEN), headers=headers)
    xmlData = xmltodict.parse(result.content)
    
    result2 = requests.get('https://plex.tv/api/users', headers=headers)
    xmlData2 = xmltodict.parse(result2.content)
    
    user_ids = {user['@id']: user.get('@username', user.get('@title')) for user in xmlData2['MediaContainer']['User']}
    users = {user_ids[user['@userID']]: user['@accessToken'] for user in xmlData['MediaContainer']['SharedServer']}

    return users

def remove_playlist(plex, playlist_name):
    for playlist in plex.playlists():
        if playlist.title == playlist_name:
            try:
                playlist.delete()
                #print("{}: Playlist deleted".format(playlist_name))
            except:
                print("ERROR - cannot delete playlist: {}".format(playlist_name))
                return None

def create_playlists(plex, runlist, playlist_name):
    try:
        remove_playlist(plex, playlist_name)
        plex.createPlaylist(playlist_name, runlist)
    except:
        print ("""
        ERROR trying to create playlist '{0}'
        The number of movies/shows in the list provided was {1}
        """.format(
            playlist_name,
            len(runlist)
        ))

def loop_plex_users(plex, list, playlist_name):
    #update my list
    create_playlists(plex, list, playlist_name)

    #update list for shared users
    if SYNC_WITH_SHARED_USERS:
        plex_users = get_user_tokens(plex.machineIdentifier)
        for user in plex_users:
            if (not ALLOW_SYNCED_USERS or user in ALLOW_SYNCED_USERS) and user not in NOT_ALLOW_SYNCED_USERS:
                print("{}: updating playlist for user {}".format(playlist_name, user))
                user_token = plex_users[user]
                user_plex = PlexServer(baseurl=PLEX_URL, token=user_token, timeout=PLEX_TIMEOUT)
                create_playlists(user_plex, list, playlist_name)
    else:
        print("Skipping adding to shared users")

def get_tvdb_id(show):
    tvdb_id = None
    last_episode = show.episodes()[-1]
    if last_episode.guid != NA and 'thetvdb://' in last_episode.guid:
        tvdb_id = last_episode.guid.split('thetvdb://')[1].split('?')[0].split('/')[0]
    return tvdb_id

def setup_show_playlist(plex, tvdb_ids, plex_shows, playlist_name):
    if tvdb_ids:
        # Create a list of matching shows using last episode
        print("{}: finding matching episodes for playlist with count {}".format(playlist_name, len(tvdb_ids)))
        matching_episodes = []
        matching_episode_ids = []
        sorted_shows = []
        for show in plex_shows:
            tvdb_id = get_tvdb_id(show)

            if tvdb_id and tvdb_id in tvdb_ids:
                matching_episodes.append(show.episodes()[-1])
                matching_episode_ids.append(tvdb_id)

        missing_episode_ids = list(set(tvdb_ids) - set(matching_episode_ids))
        print("I found {match_len} of your episode IDs that matched the TVDB IDs top {tvdb_len} list".format(match_len=len(matching_episode_ids), tvdb_len=len(tvdb_ids)))
        print("That means you are missing {missing_len} of the TVDB IDs top {tvdb_len} list".format(missing_len=len(missing_episode_ids), tvdb_len=len(tvdb_ids)))
        if len(missing_episode_ids) > 0:
            print("The TVDB IDs are listed below .. You can copy/paste this info and put into sonarr ..")
            for tvdb_id in missing_episode_ids:
                print("tvdb: {}".format(tvdb_id))

        print("{}: Sorting list in correct order".format(playlist_name))

        for tvdb_id in tvdb_ids:
            for episode in matching_episodes:
                show_tvdb_id = episode.guid.split('thetvdb://')[1].split('?')[0].split('/')[0]
                if show_tvdb_id == tvdb_id:
                    sorted_shows.append(episode)
                    break;

        print("{}: Created shows list".format(playlist_name))

        loop_plex_users(plex, sorted_shows, playlist_name)
    else:
        print('{}: WARNING - Playlist is empty'.format(playlist_name))

def get_imdb_id(movie):
    try:
        imdb_id = "tt" + re.search(r'tt(\d+)\?', movie.guid).group(1)
    except:
        imdb_id = None
    return imdb_id

def append_movie_id_dict(movie, movie_id_dict):
    log_timer("start append movie id dict")
    imdb_id = get_imdb_id(movie)
    if imdb_id != None:
        movie_id_dict[imdb_id] = movie
    log_timer("end append movie id dict")
    return movie_id_dict

def create_movie_id_dict(movies):
    movie_id_dict = {}
    log_timer("start create movie id dict")
    for movie in movies:
        movie_id_dict = append_movie_id_dict(movie, movie_id_dict)
    log_timer("end create movie id dict")
    return movie_id_dict

def get_matching_movies(imdb_ids, movie_id_dict):
    movies = []
    movie_ids = []
    for imdb_id in imdb_ids:
        if imdb_id in movie_id_dict:
            movies.append(movie_id_dict[imdb_id])
            movie_ids.append(imdb_id)
    returnme = []
    returnme.append(movies)
    returnme.append(movie_ids)
    return returnme

def print_imdb_info(matching_movie_ids, imdb_ids):
    missing_imdb_ids = list(set(imdb_ids) - set(matching_movie_ids))
    print ("""
    I found {match_ids_len} of your movie IDs that matched
    the IMDB IDs top {imdb_ids_len} list ..
    That means you are missing {miss_ids_len} of
    the IMDB IDs top {imdb_ids_len} list
    """.format(
        match_ids_len=len(matching_movie_ids),
        imdb_ids_len=len(imdb_ids),
        miss_ids_len=len(missing_imdb_ids)
    ))
    print_missing_imdb_info(missing_imdb_ids)

def print_missing_imdb_info(missing_imdb_ids):
    if len(missing_imdb_ids) > 0:
        print ("""
        The IMDB IDs are listed below .. You can
        copy/paste this info and put into radarr ..
        """)
        for imdb_id in missing_imdb_ids:
            print ("imdb: {0}".format(imdb_id))
        print ("\n\n")

def setup_movie_playlist2(plex, imdb_ids, movie_id_dict, playlist_name):
    if imdb_ids:
        print ("{0}: finding matching movies for playlist with count {1}".format(
            playlist_name,
            len(imdb_ids)
        ))

        matches = get_matching_movies(imdb_ids, movie_id_dict)
        matching_movies = matches[0]
        matching_movie_ids = matches[1]

        print_imdb_info(matching_movie_ids, imdb_ids)

        print ("{}: Created movie list".format(playlist_name))
        log_timer()

        loop_plex_users(plex, matching_movies, playlist_name)
    else:
        print ("{0}: WARNING - Playlist is empty".format(playlist_name))

def trakt_watched_imdb_id_list():
    # Get the weekly watched list
    print("Retrieving the Trakt weekly list...")
    imdb_ids = []

    headers = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': TRAKT_API_KEY
    }

    request = Request('https://api.trakt.tv/movies/watched/weekly?page=1&limit={}'.format(TRAKT_NUM_MOVIES), headers=headers)
    try:
        response = urlopen(request)
        trakt_movies = json.load(response)

        # loop through movies and add movies to list if match
        for movie in trakt_movies:
            imdb_ids.append(movie['movie']['ids']['imdb'])
    except:
        print ("Bad Trakt Code")
        return []

    return imdb_ids

def trakt_popular_imdb_id_list():
    # Get the weekly watched list
    print("Retrieving the Trakt popular list...")
    imdb_ids = []

    headers = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': TRAKT_API_KEY
    }

    try:
        request = Request('https://api.trakt.tv/movies/popular?page=1&limit={}'.format(TRAKT_NUM_MOVIES), headers=headers)
        response = urlopen(request)
        trakt_movies = json.load(response)

        # loop through movies and add movies to list if match
        for movie in trakt_movies:
            imdb_ids.append(movie['ids']['imdb'])
    except:
        print ("Bad Trakt Code")
        return []

    return imdb_ids

def trakt_watched_show_imdb_id_list():
    # Get the weekly watched list
    print("Retrieving the Trakt weekly list...")
    tvdb_ids = []

    headers = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': TRAKT_API_KEY
    }
    try:
        request = Request('https://api.trakt.tv/shows/watched/weekly?page=1&limit={}'.format(TRAKT_NUM_SHOWS), headers=headers)
        response = urlopen(request)
        trakt_show = json.load(response)

        # loop through movies and add movies to list if match
        for show in trakt_show:
            tvdb_ids.append(str(show['show']['ids']['tvdb']))
    except:
        print ("Bad Trakt Code")
        return []

    return tvdb_ids

def trakt_popular_show_imdb_id_list():
    # Get the weekly watched list
    print("Retrieving the Trakt popular list...")
    tvdb_ids = []

    headers = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': TRAKT_API_KEY
    }

    try:
        request = Request('https://api.trakt.tv/shows/popular?page=1&limit={}'.format(TRAKT_NUM_SHOWS), headers=headers)
        response = urlopen(request)
        trakt_show = json.load(response)

        # loop through movies and add movies to list if match
        for show in trakt_show:
            tvdb_ids.append(str(show['ids']['tvdb']))
    except:
        print ("Bad Trakt Code")
        return []

    return tvdb_ids

def imdb_search_list(url):
    response = urlopen(url)
    data = response.read()
    response.close()
    doc = lxml.html.document_fromstring(data)
    ids = doc.xpath("//img[@class='loadlate']/@data-tconst")
    return ids

def imdb_search_list_name(url):
    response = urlopen(url)
    data = response.read()
    response.close()
    doc = lxml.html.document_fromstring(data)
    name = doc.xpath("//h1[contains(@class, 'header')]")[0].text.strip()
    return name

def imdb_search_lists(plex, movie_id_dict):
    for list in IMDB_SEARCH_LISTS:
        url = list.split("||")[0]
        try:
            name = runlist.split("||")[1]
        except:
            name = imdb_search_list_name(url)

        print ("Creating IMDB search playlist '{0}' using URL {1}".format(
            name,
            url
        ))

        ids = imdb_search_list(url)
        setup_movie_playlist2(plex, ids, movie_id_dict, "IMDB - {0}".format(name))

def imdb_chart_list(url):
    response = urlopen(url)
    data = response.read()
    response.close()
    doc = lxml.html.document_fromstring(data)
    ids = doc.xpath("//table[contains(@class, 'chart')]//td[@class='ratingColumn']/div//@data-titleid")
    return ids

def imdb_chart_list_name(url):
    response = urlopen(url)
    data = response.read()
    response.close()
    doc = lxml.html.document_fromstring(data)
    name = doc.xpath("//h1[contains(@class, 'header')]")[0].text.strip()
    return name

def imdb_chart_lists(plex, movie_id_dict):
    for runlist in IMDB_CHART_LISTS:
        url = runlist.split(",")[0]
        try:
            name = runlist.split(",")[1]
        except:
            name = imdb_chart_list_name(url)

        print ("Creating IMDB chart playlist '{0}' using URL {1}".format(
            name,
            url
        ))

        ids = imdb_chart_list(url)
        setup_movie_playlist2(plex, ids, movie_id_dict, "IMDB - {0}".format(name))

def imdb_custom_list(url):
    response = urlopen(url)
    data = response.read()
    response.close()
    doc = lxml.html.document_fromstring(data)
    ids = doc.xpath("//div[contains(@class, 'lister-item-image ribbonize')]/@data-tconst")
    return ids

def imdb_custom_list_name(url):
    response = urlopen(url)
    data = response.read()
    response.close()
    doc = lxml.html.document_fromstring(data)
    name = doc.xpath("//h1[contains(@class, 'header list-name')]")[0].text.strip()
    return name

def imdb_custom_lists(plex, movie_id_dict):
    for list in IMDB_CUSTOM_LISTS:
        url = list.split(",")[0]
        try:
            name = list.split(",")[1]
        except:
            name = imdb_custom_list_name(url)

        print ("Creating IMDB custom playlist '{0}' using URL {1}".format(
            name,
            url
        ))

        ids = imdb_custom_list(url)
        setup_movie_playlist2(plex, ids, movie_id_dict, "IMDB - {0}".format(name))

def run_movies_lists(plex):
    # Get list of movies from the Plex server
    # split into array
    movie_libs = MOVIE_LIBRARY_NAME.split(",")
    all_movies = []
    log_timer()

    tmp_movie_id_dict = {}

    # loop movie lib array
    for lib in movie_libs:
        lib = lib.strip()
        print("Retrieving a list of movies from the '{library}' library in Plex...".format(library=lib))
        try:
            movie_library = plex.library.section(lib)
            new_movies = movie_library.all()
            all_movies = all_movies + new_movies
            print("Added {length} movies to your 'all movies' list from the '{library}' library in Plex...".format(library=lib, length=len(new_movies)))
            log_timer()
        except:
            print("The '{library}' library does not exist in Plex.".format(library=lib))
            print("Exiting script.")
            return [], 0

    print ("Found {0} movies total in 'all movies' list from Plex...".format(
        len(all_movies)
    ))

    print ("Creating movie dictionary based on ID")
    movie_id_dict = create_movie_id_dict(all_movies)

    print("Retrieving new lists")
    if TRAKT_API_KEY:
        trakt_weekly_imdb_ids = trakt_watched_imdb_id_list()
        trakt_popular_imdb_ids = trakt_popular_imdb_id_list()
        setup_movie_playlist2(plex, trakt_weekly_imdb_ids, movie_id_dict, TRAKT_WEEKLY_PLAYLIST_NAME)
        setup_movie_playlist2(plex, trakt_popular_imdb_ids, movie_id_dict, TRAKT_POPULAR_PLAYLIST_NAME)
    else:
        print("No Trakt API key, skipping lists")

    imdb_search_lists(plex, movie_id_dict)
    imdb_chart_lists(plex, movie_id_dict)
    imdb_custom_lists(plex, movie_id_dict)

def run_show_lists(plex):
    # Get list of shows from the Plex server
    # split into array
    show_libs = SHOW_LIBRARY_NAME.split(",")
    all_shows = []
    log_timer()
    # loop movie lib array
    for lib in show_libs:
        lib = lib.strip()
        print("Retrieving a list of shows from the '{library}' library in Plex...".format(library=lib))
        try:
            show_library = plex.library.section(lib)
            new_shows = show_library.all()
            all_shows = all_shows + new_shows
            print("Added {length} shows to your 'all shows' list from the '{library}' library in Plex...".format(library=lib, length=len(new_shows)))
            log_timer()
        except:
            print("The '{library}' library does not exist in Plex.".format(library=lib))
            print("Exiting script.")
            return [], 0

    print ("Found {0} show total in 'all shows' list from Plex...".format(
        len(all_shows)
    ))

    print("Retrieving new lists")
    if TRAKT_API_KEY:
        trakt_weekly_show_imdb_ids = trakt_watched_show_imdb_id_list()
        trakt_popular_show_imdb_ids = trakt_popular_show_imdb_id_list()
        setup_show_playlist(plex, trakt_weekly_show_imdb_ids, all_shows, TRAKT_WEEKLY_SHOW_PLAYLIST_NAME)
        setup_show_playlist(plex, trakt_popular_show_imdb_ids, all_shows, TRAKT_POPULAR_SHOW_PLAYLIST_NAME)
        # setup_show_playlist2(plex, trakt_weekly_show_imdb_ids, show_id_dict, TRAKT_WEEKLY_SHOW_PLAYLIST_NAME)
        # setup_show_playlist2(plex, trakt_popular_show_imdb_ids, show_id_dict, TRAKT_POPULAR_SHOW_PLAYLIST_NAME)
    else:
        print ("No Trakt API key, skipping lists")

def list_remover(plex, playlist_name):
    #update my list
    print("{}: removing playlist for script user".format(playlist_name))
    remove_playlist(plex, playlist_name)

    #update list for shared users
    if SYNC_WITH_SHARED_USERS:
        plex_users = get_user_tokens(plex.machineIdentifier)
        for user in plex_users:
            if (not ALLOW_SYNCED_USERS or user in ALLOW_SYNCED_USERS):
                print ("{0}: removing playlist for user {1}".format(
                    playlist_name,
                    user
                ))
                user_token = plex_users[user]
                user_plex = PlexServer(baseurl=PLEX_URL, token=user_token, timeout=PLEX_TIMEOUT)
                remove_playlist(user_plex, playlist_name)
            else:
                print ("{0}: NOT removing playlist for user {1}".format(
                    playlist_name,
                    user
                ))
    else:
        print("Skipping removal from shared users")

def imdb_playlist_remover(plex, name):
    list_remover(plex, name)
    list_remover(plex, "IMDB Custom List - {0}".format(name))
    list_remover(plex, "IMDB Chart - {0}".format(name))
    list_remover(plex, "IMDB Search List - {0}".format(name))
    list_remover(plex, "IMDB - {0}".format(name))

def remove_lists(plex):
    for showlist in IMDB_CUSTOM_LISTS:
        url = showlist.split(",")[0]
        try:
            name = showlist.split(",")[1]
        except:
            name = imdb_custom_list_name(url)
        print ("Removing IMDB custom playlist '{0}'".format(
            name
        ))
        imdb_playlist_remover(plex, name)

    for showlist in IMDB_CHART_LISTS:
        url = showlist.split(",")[0]
        try:
            name = showlist.split(",")[1]
        except:
            name = imdb_chart_list_name(url)
        print ("Removing IMDB chart playlist '{0}'".format(
            name
        ))
        imdb_playlist_remover(plex, name)

    for showlist in IMDB_SEARCH_LISTS:
        url = showlist.split("||")[0]
        try:
            name = showlist.split("||")[1]
        except:
            name = imdb_search_list_name(url)
        print ("Removing IMDB search playlist '{0}'".format(
            name
        ))
        imdb_playlist_remover(plex, name)

def list_updater():
    try:
        plex = PlexServer(baseurl=PLEX_URL, token=PLEX_TOKEN, timeout=PLEX_TIMEOUT)
    except:
        print("No Plex server found at: {base_url} or bad plex token code".format(base_url=PLEX_URL))
        print("Exiting script.")
        raw_input("press enter to exit")
        return [], 0

    if REMOVE_ONLY:
        list_remover(plex, TRAKT_WEEKLY_PLAYLIST_NAME)
        list_remover(plex, TRAKT_POPULAR_PLAYLIST_NAME)
        list_remover(plex, TRAKT_WEEKLY_SHOW_PLAYLIST_NAME)
        list_remover(plex, TRAKT_POPULAR_SHOW_PLAYLIST_NAME)
        list_remover(plex, 'Movies All Time')
        list_remover(plex, 'Best Picture Winners')
        list_remover(plex, 'IMDB - [<Element h1 at 0x7efc45fa7730>]')
        remove_lists(plex)
    else:
        run_movies_lists(plex)
        run_show_lists(plex)

if __name__ == "__main__":
    print("===================================================================")
    print("   Automated Playlist to Plex script   ")
    print("===================================================================\n")

    list_updater()

    print("\n===================================================================")
    print("                               Done!                               ")

    log_timer()

    print("===================================================================\n")
