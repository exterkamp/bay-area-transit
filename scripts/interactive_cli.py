import configparser
import requests
import codecs
import urllib.parse
import json

config = configparser.ConfigParser()
# your cfg file here.
config.read_file(open('../secrets/api.cfg'))
apiKey = config.get("api", "API_KEY")
base_url = config.get("api", "BASE_URL")

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
    getOperatorsUrl = buildApiRequestUrl("/gtfsoperators", {"api_key": apiKey})
    return callApiAndParseJsonResponse(getOperatorsUrl)

def getLines(operator_id):
    getCalTrainLinesUrl = buildApiRequestUrl("/lines", {"api_key": apiKey, "operator_id": operator_id})
    return callApiAndParseJsonResponse(getCalTrainLinesUrl)

def getTimeTableForLine(operator_id, line_id):
    getCaltrainTimeTable = buildApiRequestUrl("/timetable", {"api_key": apiKey, "operator_id": operator_id, "line_id": line_id})
    return callApiAndParseJsonResponse(getCaltrainTimeTable)

def getStops(operator_id, line_id):
    getStopsUrl = buildApiRequestUrl("/stops", {"api_key": apiKey, "operator_id": operator_id, "line_id": line_id})
    return callApiAndParseJsonResponse(getStopsUrl)

def getPatternForLine(operator_id, line_id):
    getPatternsUrl = buildApiRequestUrl("/patterns", {"api_key": apiKey, "operator_id": operator_id, "line_id": line_id})
    return callApiAndParseJsonResponse(getPatternsUrl)

# interactor loop
while True:
    user_action = input('Type command: ')
    if user_action == "exit":
        break
    elif user_action == "operators":
        for operator in getOperators():
            print(f"({operator['Id']}) {operator['Name']}")
    elif user_action == "lines":
        operator_id = input('Which Operator?')
        for line in getLines(operator_id):
            print(f"({line['Id']}) {line['Name']}")
    elif user_action == "stops":
        operator_id = input('Which Operator?')
        line_id = input('Which Line?')
        stops = getStops(operator_id, line_id)["Contents"]["dataObjects"]["ScheduledStopPoint"]
        for stop in stops:
            print(f"({stop['id']}) {stop['Name']}")
    else:
        print(f"unknown command: {user_action}")

print("Goodbye.")