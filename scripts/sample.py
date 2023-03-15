import configparser
import requests
import codecs
import urllib.parse
import json
import time as timetime
from datetime import datetime, time
# from datetime import time

config = configparser.ConfigParser()
# your cfg file here.
config.read_file(open('../secrets/api.cfg'))
apiKey = config.get("api", "API_KEY")
base_url = config.get("api", "BASE_URL")

def readCachedResponseFile(filename):
    f = open(filename)
    return json.load(f)

def buildApiRequestUrl(path, params):
    params["format"] = "json"
    url =  base_url + path + "?" + urllib.parse.urlencode(params)
    print(url)
    return url

def callApiAndParseJsonResponse(url):
    r = requests.get(url)
    # print(r.status_code, r.encoding, r.headers['content-type'])
    # Set our encoding.
    r.encoding = 'utf-8-sig'
    res = r.json()
    return res

def getOperators():
    getOperatorsUrl = buildApiRequestUrl("/gtfsoperators", {"api_key": apiKey})
    return callApiAndParseJsonResponse(getOperatorsUrl)

def getLines(operator_id):
    getCalTrainLinesUrl = buildApiRequestUrl("/lines", {"api_key": apiKey, "operator_id": "CT"})
    return callApiAndParseJsonResponse(getCalTrainLinesUrl)

def getTimeTableForLine(operator_id, line_id):
    getCaltrainTimeTable = buildApiRequestUrl("/timetable", {"api_key": apiKey, "operator_id": operator_id, "line_id": line_id})
    return callApiAndParseJsonResponse(getCaltrainTimeTable)

def getStops(operator_id, line_id):
    getStopsUrl = buildApiRequestUrl("/stopplaces", {"api_key": apiKey, "operator_id": operator_id, "line_id": line_id})
    return callApiAndParseJsonResponse(getStopsUrl)

def getPatternForLine(operator_id, line_id):
    getPatternsUrl = buildApiRequestUrl("/patterns", {"api_key": apiKey, "operator_id": operator_id, "line_id": line_id})
    return callApiAndParseJsonResponse(getPatternsUrl)

# for operator in getOperators():
#     identifier = operator['Id']
#     name = operator['Name']
#     print("(",identifier,")", name)

# # Get CalTrain lines.
# for line in getLines("CT"):
#     identifier = line['Id']
#     name = line['Name']
#     mode = line['TransportMode']
#     publicCode = line['PublicCode']
#     siriLineRef = line['SiriLineRef']
#     monitored = line['Monitored']
#     print("(",identifier,")", name)

# Get CalTrain Local Line Timetable
# timeTable = getTimeTableForLine("CT", "L2")
# print(timeTable)

# http://api.511.org/transit/vehiclepositions?api_key=[your_key]&agency=[operatorID]

# stops = getStops("CT", "L2")["Siri"]["ServiceDelivery"]["DataObjectDelivery"]["dataObjects"]["SiteFrame"]["stopPlaces"]["StopPlace"]

# # {
# #   "Siri": {
# #     "ServiceDelivery": {
# #       "ResponseTimestamp": "2023-03-09T10:24:27-08:00",
# #       "DataObjectDelivery": {
# #         "ResponseTimestamp": "2023-03-09T10:24:27-08:00",
# #         "dataObjects": {
# #           "SiteFrame": {
# #             "@version": "any",
# #             "@id": "CT",
# #             "stopPlaces": {

# for stop in stops:
#     print(stop)

s = readCachedResponseFile("cached_stops_L2.json")["Contents"]["dataObjects"]["ScheduledStopPoint"]

stopPointsById = {}

for stop in s:
    stopPointsById[stop["id"]] = stop

# for _, stop in stopPointsById.items():
#     print(f"{stop['Name']}")

p = readCachedResponseFile("cached_patterns_L2.json") # getPatternForLine("CT", "L2")
# print(p)

directions = p["directions"]
journeys = p["journeyPatterns"]

journeysSortedByDirection = {}

for direction in directions:
    journeysSortedByDirection[direction["DirectionId"]] = []

for journey in journeys:
    jDir = journey["DirectionRef"]
    journeysSortedByDirection[jDir].append(journey)

for direction, journeys in journeysSortedByDirection.items():
    print(direction)
    for journey in journeys:
        points = journey["PointsInSequence"]["TimingPointInJourneyPattern"]
        starting_point = points[0]
        print(f"\t{starting_point['Name']} -> {journey['DestinationDisplayView']['FontText']}")
        print(f"\t\tstops: {len(points)}")
        # patternStr = []
        # for point in points:
        #     patternStr.append(point['ScheduledStopPointRef'])
        #     # print(f"\t\t({point['ScheduledStopPointRef']}) - {point['Name']}")
        # print(f"\t\t{', '.join(patternStr)}")
t = readCachedResponseFile("cached_timetable_L2.json")["Content"] # getPatternForLine("CT", "L2")

routes = t["ServiceFrame"]["routes"]["Route"]

# print("L2 Routes")
# for route in routes:
#     print(f"({route['id']}) - {route['Name']}")

timetable = t["TimetableFrame"]
for entry in timetable:
    print(f"({entry['id']}) - {entry['Name']}")
    journeys = entry["vehicleJourneys"]["ServiceJourney"]
    for journey in journeys:
        calls = journey["calls"]["Call"]
        
        # start_time = time.strptime(calls[0]['Arrival']['Time'], '%H:%M:%S')
        # end_time = time.strptime(calls[-1]['Arrival']['Time'], '%H:%M:%S')
        
        start_time = time.fromisoformat(calls[0]['Arrival']['Time'])
        startDaysOffset = int(calls[0]['Arrival']['DaysOffset'])

        # maybe days offset        
        end_time = time.fromisoformat(calls[-1]['Arrival']['Time'])
        endDaysOffset = int(calls[-1]['Arrival']['DaysOffset'])

        start_datetime = datetime.combine(datetime(1,1,1+startDaysOffset), start_time)
        end_datetime = datetime.combine(datetime(1,1,1+endDaysOffset), end_time)

       
        
        duration = (end_datetime - start_datetime).total_seconds()
        # str(datetime.timedelta(seconds=666))
        
        # timetime.strptime('%S', str(duration.total_seconds()))
        # start_time = 
        # end_time = calls[-1]['Arrival']['Time']
        # duration = end_time - start_time

        print(f"vic: {journey['id']} {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')} ({timetime.strftime('%Hh %Mm', timetime.gmtime(duration))})")
        
        # for call in :
        #     stopPointRef = call['ScheduledStopPointRef']['ref']
        #     stopPoint = stopPointsById[stopPointRef]
        #     print(f"\t{call['Arrival']['Time']} @ {stopPoint['Name']}")

