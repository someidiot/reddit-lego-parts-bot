#!/usr/bin/env python

import praw
import OAuth2Util
import re
import configparser
import datetime
import requests


CONFIG_FILE = 'config.ini'

def get_parts(text):
    # (?:^|\s) = part must be start of a new word
    # \d{3,} = Must start with at least 3 digits (not interested in ancient parts, avoid lots of false hits)
    # [0-9a-z]* = Can have any lower case alphas/digits after the initial digits
    parts = re.findall(r'(?:^|\s)(\d{3,}[0-9a-z]*)', text)
    #print(parts)
    return list(set(parts))


def log(msg):
    print(datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S") + ' - ' + msg)


def get_part_details(part_id):
    url = "https://rebrickable.com/api/get_part?key=" + RB_API_KEY + "&format=json&part_id=" + part_id
    r = requests.get(url)
    if r.status_code == 200:
        if r.text == "NOPART":
            return {}
        else:
            return r.json()


# Some tests to make sure the regex works for all cases
assert(get_parts('3001') == ['3001'])
assert(get_parts('6538b') == ['6538b'])
assert(get_parts('92817pr0004c01') == ['92817pr0004c01'])
assert(get_parts('32310pb01') == ['32310pb01'])
assert(get_parts('970c153pr0750') == ['970c153pr0750'])
assert(get_parts('http://6114143.jpg') == [])
assert(get_parts('part 3001 yay.') == ['3001'])
assert(get_parts('3001?') == ['3001'])
assert(get_parts('1') == [])
assert(get_parts('111') == ['111'])
assert(get_parts('$111') == [])
assert(get_parts('$4073') == [])

log("Logging in")
user_agent = "python:legoparts:v1.0 (by /u/someotheridiot) "
r = praw.Reddit(user_agent=user_agent)
o = OAuth2Util.OAuth2Util(r)
o.refresh(force=True)

#subreddits = ['legopartsbottest', 'lego']
subreddits = ['legopartsbottest']

config = configparser.ConfigParser()
config.read(CONFIG_FILE)
if "rebrickable" in config:
    RB_API_KEY = config["rebrickable"].get('api_key', "")
else:
    RB_API_KEY = ""


for subreddit in subreddits:

    log("")
    log("Scanning /r/" + subreddit)

    sub = r.get_subreddit(subreddit)
    sub_comments = sub.get_comments()

    if subreddit in config:
        last_processed_time = float(config[subreddit].get('last_processed_time', 0))
    else:
        last_processed_time = 0
    new_last_processed_time = last_processed_time
    log("last processed time = " + str(last_processed_time))

    first = True
    for comment in sub_comments:
        # Comments in reverse chronological order (most recent first)
        if first:
            new_last_processed_time = comment.created_utc
        first = False

        log(comment.id)
        log(" Time: " + str(comment.created_utc))
        if comment.created_utc <= last_processed_time:
            log("Already processed, exiting")
            break

        log(" By: " + comment.author.name)
        if comment.author.name in ['LegoLinkBot', 'legopartsbot']:
            log("Skipping")
            continue

        log(" Body: " + comment.body)
        parts = get_parts(comment.body)

        if parts:
            log(" Found parts: " + " ".join(parts))
            reply = "Part ID | Image | Name | Years\n"
            reply += "--|--|--|--\n"
            num_found = 0
            for part in parts:
                part_details = get_part_details(part)
                if part_details and 'part_url' in part_details:
                    reply += "[" + part + "](" + part_details['part_url'] + ")|"
                    reply += "[img](" + part_details['part_img_url'] + ")|"
                    reply += part_details['name'] + "|"
                    reply += part_details['year1'] + " to " + part_details['year2'] + "\n"
                    num_found += 1
            reply += "*****\n"
            reply += "I'm a bot! I try to identify LEGO part numbers in comments and display details of those parts using the [Rebrickable API](https://rebrickable.com). Created by /u/someotheridiot"
            if num_found > 0:
                log(" Replying for " + str(num_found) + " parts")
                comment.reply(reply)


    config[subreddit] = {'last_processed_time': new_last_processed_time}

    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)
