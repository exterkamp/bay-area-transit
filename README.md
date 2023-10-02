# bay-area-transit

## Create your API key secrets cfg

```
$ touch secrets/api.cfg
```

config to add:

```
[api]
API_KEY=...
BASE_URL=https://api.511.org
```

## Get a feed

By default `CT` is the only feed pulled.

```sh
$ python scripts/import_gtfs.py
```