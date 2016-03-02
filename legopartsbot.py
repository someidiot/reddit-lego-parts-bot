#!/usr/bin/env python

import praw
import OAuth2Util
import re
import configparser
import datetime
import requests
import time


CONFIG_FILE = 'config.ini'


def log(msg):
    print(datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S") + ' - ' + msg)


def already_replied(comment):
    for c in comment.replies:
        if c.author.name == 'legopartsbot':
            return True
    return False


def get_part_details(part_id):
    url = "https://rebrickable.com/api/get_part?key=" + RB_API_KEY + "&format=json&part_id=" + part_id + "&inc_colors=0&inc_cost=1"
    r = requests.get(url)
    if r.status_code == 200:
        #log(r.text)
        if r.text == "NOPART":
            return {}
        else:
            # Valid part, make sure it's not a valid set too (which is the most common use case of the number)
            url = "https://rebrickable.com/api/get_set?key=" + RB_API_KEY + "&format=json&set_id=" + part_id + "-1"
            s = requests.get(url)
            if s.status_code == 200:
                #log(s.text)
                if s.text == "NOSET":
                    # Keep the part
                    return r.json()
                else:
                    return {}
    return {}


def get_parts(text):
    # (?:^|\s) = part must be start of a new word
    # \d{3,} = Must start with at least 3 digits (not interested in ancient parts, avoid lots of false hits)
    # [0-9a-z]* = Can have any lower case alphas/digits after the initial digits
    # (?:$|\s|\.|\?) = must end with whitespace or terminal punctuation (but not eg 299.99)
    parts = re.findall(r'(?:^|\s)(\d{3,}[0-9a-z]*)(?:$|\s|\.\s|\?)', text)

    # BrickLink URLs
    # (?:P=) = Start with P= (url param)
    # (?:$|\s|\.\s|\?|&|##|\)) = End with whitespace or next URL param
    parts.extend(re.findall(r'(?:P=)(\d{3,}[0-9a-z]*)(?:$|\s|\.\s|\?|&|#|\))', text))

    # Rebrickable URLs
    # (?:rebrickable.com\/parts\/) = Start with rebrickable.com/parts/
    # (?:$|\s|\.\s|/|\)) = End with whitespace or /
    parts.extend(re.findall(r'(?:rebrickable.com\/parts\/)(\d{3,}[0-9a-z]*)(?:$|\s|\.\s|/|\))', text))

    # De-dup the list
    parts = list(set(parts))

    # My regex skills can only go so far... further prune parts list
    # Get a list of all words, split on alphanumeric or whitespace
    all_words = re.compile(r'[\s\W]+').split(text)
    #log("Words = " + str(all_words))
    for p in parts[:]:
        if p in ['2013','2014','2015','2016','2017','2018','2019','2020']:
            # Years
            parts.remove(p)
        if p[-2:] == '00' or p[-3:] == '000' or p[-4:] == '0000':
            # Exclude round numbers like 200, 600, 4000 as they are most likely not referring to parts
            parts.remove(p)
        
        # Look at surrounding words
        i = all_words.index(p)
        
        if len(all_words)>i+1 and all_words[i+1].lower() in ['feet','inches','meters','cms','m','years','hours','hrs',
                                                             'pieces','parts']:
            parts.remove(p)
        if p == '3245' and i>=1 and all_words[i-1].lower() == 'arocs':
            # Uggghhh very specific exception "Arocs 3245" (set 42043)
            parts.remove(p)
    
    #log("Parts = " + str(parts))
    return parts


# Some tests to make sure the regex works for all cases
assert(get_parts('3001') == ['3001'])
assert(get_parts('this is part 6538b') == ['6538b'])
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
assert(get_parts('4073%') == [])
assert(get_parts('4073€') == [])
assert(get_parts('4073 is 100€') == ['4073'])
assert(get_parts('4073£') == [])
assert(get_parts('4073-4074') == [])
assert(get_parts('200-400 piece sets') == [])
assert(get_parts('2016') == [])  # year, not part
assert(get_parts('Currently we have over 1000 sets in our possession and maybe like 4000 figs.') == [])  # Just assume any round number is not a part
assert(get_parts('Super Star Destroyer: 2375 feet (3001.9 meters)') == [])
assert(get_parts('It has 2526 pieces') == [])
assert(get_parts('With a 299.99 price tag.. yeesh.') == [])
# https://www.reddit.com/r/lego/comments/40ixfb/lets_talk_about_permanent_connections_not/
assert(get_parts('https://alpha.bricklink.com/pages/clone/catalogitem.page?P=32305&idColor=10#T=C&C=10') == ['32305'])
assert(get_parts('http://alpha.bricklink.com/pages/clone/catalogitem.page?P=96874#T=S&O={}') == ['96874'])
assert(get_parts('https://alpha.bricklink.com/pages/clone/catalogitem.page?P=6538c#T=C') == ['6538c'])
assert(get_parts('http://rebrickable.com/parts/4212b') == ['4212b'])
assert(get_parts('http://rebrickable.com/parts/4212b/blah') == ['4212b'])
assert(get_parts('truck. [Here is the frame.](http://rebrickable.com/parts/4212b) It') == ['4212b'])
assert(get_parts('the Mercedes-Benz Arocs 3245 (Technic set 42043) as that') == [])

log("Logging in")
user_agent = "python:legoparts:v1.1 (by /u/someotheridiot) "
r = praw.Reddit(user_agent=user_agent)
o = OAuth2Util.OAuth2Util(r)
o.refresh(force=True)

subreddits = ['legopartsbottest', 'lego']
#subreddits = ['legopartsbottest']

config = configparser.ConfigParser()
config.read(CONFIG_FILE)
if "rebrickable" in config:
    RB_API_KEY = config["rebrickable"].get('api_key', "")
else:
    RB_API_KEY = ""

while True:
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


        # Just focus on specific thread
        if False:
            submission = r.get_submission(submission_id='40ixfb')
            submission.replace_more_comments(limit=None, threshold=0)
            sub_comments = submission.comments
            last_processed_time = 0

        first = True
        try:
            for comment in sub_comments:
                # Comments in reverse chronological order (most recent first)
                if first:
                    new_last_processed_time = comment.created_utc
                first = False

                log(comment.id)
                log(" Time: " + str(comment.created_utc))
                if comment.created_utc <= last_processed_time:
                    log("Already processed")
                    break

                log(" By: " + comment.author.name)
                if comment.author.name in ['LegoLinkBot', 'legopartsbot']:
                    log("Skipping bot author")
                    continue

                # Make sure I haven't already replied (timestamps handle this usually, but sometimes I rerun manually)
                if already_replied(comment):
                    log("Already replied, skipping")
                    continue


                #log(" Body: " + comment.body)
                parts = get_parts(comment.body)

                if parts:
                    log(" Found parts: " + " ".join(parts))
                    reply = "Part ID | Image | Name | Years | Median Price (USD)\n"
                    reply += "--|--|--|--|--\n"
                    num_found = 0
                    for part in parts:
                        part_details = get_part_details(part)
                        #log(str(part_details))
                        if part_details and 'part_url' in part_details:
                            reply += "[" + part + "](" + part_details['part_url'] + ")|"
                            reply += "[img](" + part_details['part_img_url'] + ")|"
                            reply += part_details['name'] + "|"
                            if part_details['year1'] != 0 and part_details['year2'] != 0:
                                reply += str(part_details['year1']) + " to " + str(part_details['year2']) + "|"
                            reply += "$" + part_details['part_costs']['median_cost']
                            reply += "\n"
                            num_found += 1
                    reply += "*****\n"
                    reply += "I'm a bot! I try to identify LEGO part numbers in comments and display details of those parts using the [Rebrickable API](https://rebrickable.com). Created by /u/someotheridiot"
                    if num_found > 0:
                        log(" REPLYING for " + str(num_found) + " parts")
                        try:
                            comment.reply(reply)
                            time.sleep(30)
                        except praw.errors.RateLimitExceeded:
                            log("Rate limited... waiting a bit")
                            time.sleep(600)
                            try:
                                comment.reply(reply)
                                time.sleep(30)
                            except praw.errors.RateLimitExceeded:
                                log("Dang... give up")

        except Exception as e:
            # Can't connect to Reddit... just sleep and try again
            log("Exception: " + str(e))
            pass

        config[subreddit] = {'last_processed_time': new_last_processed_time}

        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)

    # Wait and run again
    log("Sleeping")
    time.sleep(120)
