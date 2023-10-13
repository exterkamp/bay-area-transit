from django.db import models
import time
import os
import logging

from .feed_info import FeedInfo
from .agency import Agency
from .route import Route
from .stop import Stop
from .stop_time import StopTime
from .service import Service
from .service_date import ServiceDate
from .trip import Trip
from .frequency import Frequency
from .fare import Fare, FareRule
from .transfer import Transfer
from .shape import ShapePoint, post_save_shapepoint
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)


class Feed(models.Model):
    """Represents a single GTFS feed.

    This data is not part of the General Transit Feed Specification.  It is
    used to allow storage of several GTFS feeds in the same database.
    """
    operator_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)


    def __str__(self):
        if self.name:
            return f"{self.id} {self.name} @ {self.created}"
        else:
            return "%d" % self.id


    def import_gtfs(self, gtfs_obj):
        """Import a GTFS file as feed

        Keyword arguments:
        gtfs_obj - A path to a zipped GTFS file, a path to an extracted
            GTFS file, or an open GTFS zip file.

        Returns is a list of objects imported
        """
        total_start = time.time()

        # Determine the type of gtfs_obj
        opener = None
        filelist = None
        # if isinstance(gtfs_obj, string_types) and os.path.isdir(gtfs_obj):
        opener = open
        filelist = []
        print(f"path: {gtfs_obj}")
        for dirpath, dirnames, filenames in os.walk(gtfs_obj):
            filelist.extend([os.path.join(dirpath, f) for f in filenames])
        print(f"filelist: {filelist}")
        # else:
        #     zfile = ZipFile(gtfs_obj, 'r')
        #     opener = opener_from_zipfile(zfile)
        #     filelist = zfile.namelist()

        gtfs_order = (
            Agency, 
            Stop, 
            Route,
            Service,
            ServiceDate,
            ShapePoint,
            Trip,
            StopTime,
            Frequency, 
            Fare,
            FareRule,
            Transfer, 
            FeedInfo,
        )
        post_save.disconnect(dispatch_uid='post_save_shapepoint')
        # post_save.disconnect(dispatch_uid='post_save_stop')
        try:
            for klass in gtfs_order:
                for f in filelist:
                    if os.path.basename(f) == klass._filename:
                        start_time = time.time()
                        table = opener(f)
                        count = klass.import_txt(table, self) or 0
                        end_time = time.time()
                        logger.info(
                            'Imported %s (%d %s) in %0.1f seconds',
                            klass._filename, count,
                            klass._meta.verbose_name_plural,
                            end_time - start_time)
                        table.close()
        finally:
            post_save.connect(post_save_shapepoint, sender=ShapePoint)
        #     post_save.connect(post_save_stop, sender=Stop)

        # Update geometries
        start_time = time.time()
        for shape in self.shape_set.all():
            shape.update_geometry(update_parent=False)
        end_time = time.time()
        logger.info(
            "Updated geometries for %d shapes in %0.1f seconds",
            self.shape_set.count(), end_time - start_time)

        start_time = time.time()
        trips = Trip.objects.in_feed(self)
        for trip in trips:
            trip.update_geometry(update_parent=False)
        end_time = time.time()
        logger.info(
            "Updated geometries for %d trips in %0.1f seconds",
            trips.count(), end_time - start_time)

        start_time = time.time()
        routes = self.route_set.all()
        for route in routes:
            route.update_geometry()
        end_time = time.time()
        logger.info(
            "Updated geometries for %d routes in %0.1f seconds",
            routes.count(), end_time - start_time)

        total_end = time.time()
        logger.info(
            "Import completed in %0.1f seconds.", total_end - total_start)