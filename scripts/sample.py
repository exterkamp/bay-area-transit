import configparser
import requests
import codecs

config = configparser.ConfigParser()
# your cfg file here.
config.read_file(open('../secrets/api.cfg'))
apiKey = config.get("api", "API_KEY")

r = requests.get('http://api.511.org/transit/gtfsoperators?api_key=' + apiKey)
print(r.status_code, r.encoding, r.headers['content-type'])

# Set our encoding.
r.encoding = 'utf-8-sig'
res = r.json()

# print(res)

for operator in res:
    identifier = operator['Id']
    name = operator['Name']
    print("(",identifier,")", name)