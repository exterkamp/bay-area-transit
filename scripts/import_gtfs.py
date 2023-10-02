import configparser
import requests
import codecs
import urllib.parse
import json
from datetime import datetime, timedelta
import requests, zipfile, io
import os.path
from pathlib import Path
import os

script_path = os.path.dirname(__file__)
absolute_path = os.getcwd()
base_path = os.path.join(absolute_path, script_path)
print(f"base dir: {base_path}")

config = configparser.ConfigParser()
# your cfg file here.
config.read_file(open(os.path.join(base_path, '../secrets/api.cfg')))
apiKey = config.get("api", "API_KEY")
base_url = config.get("api", "BASE_URL")

def buildPath(path):
    return os.path.join(base_path, path)

def buildApiRequestUrl(path, params):
    params["format"] = "json"
    url =  base_url + path + "?" + urllib.parse.urlencode(params)
    return url

def callApiAndParseJsonResponse(url):
    r = requests.get(url)
    r.encoding = 'utf-8-sig'
    res = r.json()
    return res

def getOperators():
    getOperatorsUrl = buildApiRequestUrl("/transit/operators", {"api_key": apiKey})
    print(f"requesting: {getOperatorsUrl}")
    return callApiAndParseJsonResponse(getOperatorsUrl)

def downloadFeed(op_id):
    downloadFeedUrl = base_url + "/transit/datafeeds" + "?" + urllib.parse.urlencode({"api_key": apiKey, "operator_id": op_id})
    print(f"requesting: {downloadFeedUrl}")
    r = requests.get(downloadFeedUrl)
    if r.status_code != 200: 
        return None
    return r

def check_modification_file(path, seconds=600):
    if not os.path.isfile(path):
        return True
    with open(path, "r+") as last_mod:
        date_str = last_mod.readline()
        d = datetime.fromisoformat(date_str)
        diff = datetime.now() - d
        print(f"{path} time delta: {diff}")
        if diff.total_seconds() > seconds:
            return True
        return False   

if not os.path.isdir(buildPath("../data/operators")):
    os.mkdir(os.path.join(base_path,"../data/operators"))

operators_dict = None

if check_modification_file(buildPath("../data/operators/LAST_MODIFIED")):
    # download
    print('downloading operators')
    # get the GTFS operators
    operators_dict = getOperators()

    # save those operators
    operators_json = json.dumps(operators_dict, indent=4)
    
    # Writing to sample.json
    with open(buildPath("../data/operators/operators.json"), "w+") as outfile:
        outfile.write(operators_json)
    with open(buildPath("../data/operators/LAST_MODIFIED"), "w+") as outfile:
        outfile.write(str(datetime.now()))
else:
    # use existing
    print('using existing operators')
    with open(buildPath("../data/operators/operators.json"), "r") as infile:
        operators_dict = json.load(infile)

# Go through all the operators

interesting_feeds = ["CT"]

for operator in operators_dict:
    op_id = operator['Id']
    if op_id not in interesting_feeds:
        continue

    if not os.path.isdir(buildPath("../data/operators/feeds")):
        os.mkdir(buildPath("../data/operators/feeds"))

    if not check_modification_file(buildPath(f"../data/operators/feeds/{op_id}/LAST_MODIFIED")):
        print(f"using existing feeds")
        continue

    print(f"downloading feed for: {op_id}")

    zip_feed = downloadFeed(op_id)
    if zip_feed is None:
        continue
    z = zipfile.ZipFile(io.BytesIO(zip_feed.content))

    if not os.path.isdir(buildPath(f"../data/operators/feeds/{op_id}")):
        os.mkdir(buildPath(f"../data/operators/feeds/{op_id}"))

    z.extractall(buildPath(f"../data/operators/feeds/{op_id}"))

    with open(buildPath(f"../data/operators/feeds/{op_id}/LAST_MODIFIED"), "w+") as outfile:
        outfile.write(str(datetime.now()))

print("Goodbye.")