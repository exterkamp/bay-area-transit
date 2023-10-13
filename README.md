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

## Run Docker compose Stack

Run the initialization script.

```sh
$ ./init.sh
```

When you're done, bring it all down.

```sh
$ ./reset.sh
```

## Run Django App (pre-docker)

```sh
$ cd bayareatransit
$ python manage.py migrate
$ python manage.py runserver 0.0.0.0:10500
```

### Django commands

```sh
$ python bayareatransit/manage.py makemigrations
$ python bayareatransit/manage.py migrate
$ python bayareatransit/manage.py import_gtfs data/operators/feeds/CT --name=test
$ python bayareatransit/manage.py runserver 0.0.0.0:10500
```