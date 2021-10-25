import sys
import re
from datetime import datetime
from typing import Counter
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import tweepy
from collections import defaultdict
from config import create_api
from database import create_db

# Show all columns when printing dataframe objects
pd.set_option('display.max_columns', None)

# Set seaborn style
sns.set_theme(font_scale=0.65, palette="pastel")

# Create DB Engine and API Object
con = create_db(log=False)
api = create_api()


def get_all_tweets(screen_name):
    """ Get all tweets by screen_name. Max tweets up to 3250, retricted by Twitter """
    # tweet id can be repeated due to self-retweet. Can not set primary key to retweet_id
    # Create a empty dict with default empty list as values
    tweets = defaultdict(list)

    # status = tweet
    for status in tweepy.Cursor(api.user_timeline, screen_name=screen_name, tweet_mode="extended", count=200).items():
        # When using extended mode with a Retweet,
        # the full_text attribute of the Status object may be truncated
        # with an ellipsis character instead of containing the full text of the Retweet
        # To get the full text of the Retweet, dive into 'retweeted_status'
        # Check if retweeted_status exists
        is_retweet = hasattr(status, 'retweeted_status')
        # change the status root to retweeted_status
        tweets['screen_name'].append(status.user.screen_name)
        tweets['created_at'].append(
            datetime.strftime(status.created_at, '%Y-%m-%d'))
        if is_retweet:
            status = status.retweeted_status
            tweets['retweet_screen_name'].append(status.user.screen_name)
            tweets['retweet_created_at'].append(
                datetime.strftime(status.created_at, '%Y-%m-%d'))
        else:
            tweets['retweet_screen_name'].append(None)
            tweets['retweet_created_at'].append(None)

        tweets['tweet_id'].append(status.id)
        tweets['body'].append(status.full_text)
        tweets['user_id'].append(status.user.id)
        tweets['favorite_count'].append(status.favorite_count)
        tweets['retweet_count'].append(status.retweet_count)

    # Set primary key columns as index
    df = pd.DataFrame(tweets).set_index(['created_at', 'tweet_id'])
    # A temporary table for deleting the existing rows from tweets table
    df.to_sql('tweets_tmp', con, index=True, if_exists='replace')

    try:
        # delete rows that we are going to update
        con.execute(
            'DELETE FROM tweets WHERE (created_at, tweet_id) IN (SELECT created_at, tweet_id FROM tweets_tmp)')
        con.commit()

        # insert and update table
        df.to_sql('tweets', con, index=True, if_exists='append')
    except Exception as e:
        print(e)
        con.rollback()

    # dump a json file to inspect the context
    # with open('test.json', 'w') as fh:
    #     json_obj = json.dumps(test[1]._json, indent=4, sort_keys=True)
    #     fh.write(json_obj)

    # Save to a csv file for debugging
    print(df[['body', 'favorite_count']])
    df.to_csv('data.csv')

# under construction
def get_users_profile(screen_name):
    """ Get user basic profiles by screen_name """
    users = defaultdict(list)
    user = api.get_user(screen_name=screen_name)
    users['user_id'].append(user.id)
    users['screen_name'].append(user.screen_name)
    users['name'].append(user.name)
    users['location'].append(user.location)
    users['description'].append(user.description)
    users['followers_count'].append(user.followers_count)
    users['friends_count'].append(user.friends_count)
    users['statuses_count'].append(user.statuses_count)

    # Set primary key column as index
    df = pd.DataFrame(users).set_index(['user_id'])
    print(df)
    # A temporary table for deleting the existing rows from tweets table
    df.to_sql('users_profile_tmp', con, index=True, if_exists='replace')

    try:
        # delete rows that we are going to update
        con.execute(
            'DELETE FROM users_profile WHERE user_id IN (SELECT user_id FROM users_profile_tmp)')
        con.commit()

        # insert and update table
        df.to_sql('users_profile', con, index=True, if_exists='append')
    except Exception as e:
        print(e)
        con.rollback()

    # with open('record.json', 'w') as fhandler:
    #     json.dump(user._json, fhandler)

    # import pprint
    # import inspect
    # inspect the method of 'user' object
    # pprint.pprint(inspect.getmembers(user, predicate=inspect.ismethod))
    # show only 20 followers
    # for follower in user.followers():
    #     print(follower.name)


# Read the predefined keywords from ./keywords.txt line by line and store into a list.
keywords = []
with open('keywords.txt', 'r', encoding="utf-8") as fh:
    keywords = [line.strip().lower() for line in fh]

# convert a list into a single sql command for filtering the keywords
sql_keywords = ' OR '.join(
    [f'body LIKE \'%{kw.strip().lower()}%\'' for kw in keywords])


# a helper function that extracts all the keywords from a tweet and store into a string
def _get_keywords(row):
    matched_keywords = []
    for kw in keywords:
        if kw in row.lower():
            matched_keywords.append(kw)
    return ','.join(matched_keywords)


def read_data(screen_name):
    """Read data(body) based on keywords"""

    sql = \
        f"""
        SELECT created_at, body FROM tweets
            WHERE UPPER(screen_name)=UPPER('{screen_name}')
            AND ({sql_keywords})
        """
    # sql2 = f"SELECT * FROM tweets WHERE UPPER(screen_name)=UPPER('{screen_name}')"

    try:
        cur = con.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        
        df = pd.DataFrame(result, columns=['Date', 'Result'])
        df['Date'] = df['Date'].astype('datetime64')
        df.set_index('Date', inplace=True)
        df['Keywords'] = df['Result'].apply(lambda row: _get_keywords(row))
        df.to_csv("READ.csv", index=False)
        print(df)

        # count the keywords
        cnt = Counter()
        for kws in df.Keywords:
            for kw in kws.split(','):
                cnt[kw] += 1
        print(dict(cnt))

        # Visualize the top 10 keywords
        cnt_top10 = dict(cnt.most_common(10))
        plt.bar(cnt_top10.keys(), cnt_top10.values())
        plt.title('Top 10 Occurrence of Keywords')
        plt.xlabel('Keywords')
        plt.ylabel('Count')
        plt.show()

    except Exception as e:
        print(e)


def get_followers(screen_name):
    """ Get followers by screen_name """
    followers = defaultdict(list)

    for follower in tweepy.Cursor(api.get_followers, screen_name=screen_name).items():
        if follower.startwith('Rate limit reached'):
            print(follower)
            break
        else:
            follower['user_id'].append(follower.id)
            follower['screen_name'].append(follower.screen_name)
            follower['name'].append(follower.name)
            follower['location'].append(follower.location)
            follower['description'].append(follower.description)
            follower['followers_count'].append(follower.followers_count)
            follower['friends_count'].append(follower.friends_count)
            follower['statuses_count'].append(follower.statuses_count)

    # Set primary key column as index
    df = pd.DataFrame(followers).set_index(['user_id'])
    print(df)
    # # A temporary table for deleting the existing rows from tweets table
    # df.to_sql('users_profile_tmp', con, index=True, if_exists='replace')

    # try:
    #     # delete rows that we are going to update
    #     con.execute(
    #         'DELETE FROM users_profile WHERE user_id IN (SELECT user_id FROM users_profile_tmp)')
    #     con.commit()

    #     # insert and update table
    #     df.to_sql('users_profile', con, index=True, if_exists='append')
    # except Exception as e:
    #     print(e)
    #     con.rollback()


if __name__ == '__main__':
    # implement a simple command line interface
    if len(sys.argv) == 3:
        args_str = ' '.join(sys.argv[1:])
        # Regex for matching the pattern : app.py [-utr] [screen_name]
        r = re.compile('^-(?P<options>[utfr]+)\s+(?P<arg>\w+)$')
        m = r.match(args_str)
        # If there are matches
        if m is not None:
            args_dict = m.groupdict()
            # Get user profile
            # usage: python app.py -u [screen_name]
            if 'u' in args_dict['options']:
                get_users_profile(args_dict['arg'])

            # Get all tweets
            # usage: python app.py -t [screen_name]
            if 't' in args_dict['options']:
                get_all_tweets(args_dict['arg'])

            if 'f' in args_dict['options']:
                get_followers(args_dict['arg'])

            if 'r' in args_dict['options']:
                read_data(args_dict['arg'])
        else:
            print("""
                        Incorrect usage:
                        app.py [-utfr] [screen_name]
                  """)



con.close()
