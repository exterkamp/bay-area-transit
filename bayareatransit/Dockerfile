# syntax=docker/dockerfile:1
FROM python:3
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install GDAL for gis.
RUN apt-get update

RUN apt-get install -y libgdal-dev gdal-bin

RUN export CPLUS_INCLUDE_PATH=/usr/include/gdal
RUN export C_INCLUDE_PATH=/usr/include/gdal

# For testing the build.
# RUN echo "$(gdal-config --version)"

RUN pip install GDAL==$(gdal-config --version)

WORKDIR /code
COPY requirements.txt /code/
RUN pip install -r requirements.txt
COPY . /code/