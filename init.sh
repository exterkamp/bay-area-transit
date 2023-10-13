#!/usr/bin/env bash
set -x

docker compose up -d

echo "starting stack"
set +x
until [ "`docker inspect -f {{.State.Health.Status}} bay-area-transit-backend-1`" = "healthy" ]
do  
    echo "Web not healthy yet, waiting 1 second."
    sleep 1;
done;
set -x

docker compose exec backend python manage.py makemigrations

docker compose exec backend python manage.py migrate

docker compose exec backend python manage.py runscript create_superuser

# For now, import the test_data.
docker compose exec backend python manage.py import_gtfs data/operators/feeds/CT --name=test
