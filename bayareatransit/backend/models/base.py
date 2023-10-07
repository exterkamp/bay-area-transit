from django.db import models
from django.db.models.fields.related import ManyToManyField
from codecs import BOM_UTF8
from csv import reader, writer
from collections import defaultdict
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)


re_point = re.compile(r'(?P<name>point)\[(?P<index>\d)\]')
batch_size = 1000
CSV_BOM = BOM_UTF8.decode('utf-8')

class Base(models.Model):
    """Base class for models that are defined in the GTFS spec

    Implementers need to define a class variable:

    _column_map - A mapping of GTFS columns to model fields
    It should be set to a sequence of tuples:
    - GTFS column name
    - Model field name

    If the column is optional, then set blank=True on the field, and set
    null=True appropriately.

    Implementers can define this class variable:

    _rel_to_feed - The relation of this model to the field, in Django filter
    format.  The default is 'feed', and will be used to get the objects
    on a feed like this:
    Model.objects.filter(_rel_to_feed=feed)

    """

    class Meta:
        abstract = True

    # The relation of the model to the feed it belongs to.
    _rel_to_feed = 'feed'

    @classmethod
    def import_txt(cls, txt_file, feed, filter_func=None):
        '''Import from the GTFS text file'''

        # Setup the conversion from GTFS to Django Format
        # Conversion functions
        def no_convert(value): return value

        def date_convert(value): return datetime.strptime(value, '%Y%m%d')

        def bool_convert(value): return (value == '1')

        def char_convert(value): return (value or '')

        def null_convert(value): return (value or None)

        def point_convert(value):
            """Convert latitude / longitude, strip leading +."""
            if value.startswith('+'):
                return value[1:]
            else:
                return (value or 0.0)

        cache = {}

        def default_convert(field):
            def get_value_or_default(value):
                if value == '' or value is None:
                    return field.get_default()
                else:
                    return value
            return get_value_or_default

        def instance_convert(field, feed, rel_name):
            def get_instance(value):
                if value.strip():
                    related = field.related_model
                    key1 = "{}:{}".format(related.__name__, rel_name)
                    key2 = str(value)

                    # Load existing objects
                    if key1 not in cache:
                        pairs = related.objects.filter(
                            **{related._rel_to_feed: feed}).values_list(
                            rel_name, 'id')
                        cache[key1] = dict((str(x), i) for x, i in pairs)

                    # Create new?
                    if key2 not in cache[key1]:
                        kwargs = {
                            related._rel_to_feed: feed,
                            rel_name: value}
                        cache[key1][key2] = related.objects.create(
                            **kwargs).id
                    return cache[key1][key2]
                else:
                    return None
            return get_instance

        # Check unique fields
        column_names = [c for c, _ in cls._column_map]
        for unique_field in cls._unique_fields:
            assert unique_field in column_names, \
                '{} not in {}'.format(unique_field, column_names)

        # Map of field_name to converters from GTFS to Django format
        val_map = dict()
        name_map = dict()
        point_map = dict()
        for csv_name, field_pattern in cls._column_map:
            # Separate the local field name from foreign columns
            if '__' in field_pattern:
                field_base, rel_name = field_pattern.split('__', 1)
                field_name = field_base + '_id'
            else:
                field_name = field_base = field_pattern
            # Use the field name in the name mapping
            name_map[csv_name] = field_name

            # Is it a point field?
            point_match = re_point.match(field_name)
            if point_match:
                field = None
            else:
                field = cls._meta.get_field(field_base)

            # Pick a conversion function for the field
            if point_match:
                converter = point_convert
            elif isinstance(field, models.DateField):
                converter = date_convert
            elif isinstance(field, models.BooleanField):
                converter = bool_convert
            elif isinstance(field, models.CharField):
                converter = char_convert
            elif field.is_relation:
                converter = instance_convert(field, feed, rel_name)
                assert not isinstance(field, models.ManyToManyField)
            elif field.null:
                converter = null_convert
            elif field.has_default():
                converter = default_convert(field)
            else:
                converter = no_convert

            if point_match:
                index = int(point_match.group('index'))
                point_map[csv_name] = (index, converter)
            else:
                val_map[csv_name] = converter

        # Read and convert the source txt
        csv_reader = reader(txt_file, skipinitialspace=True)
        unique_line = dict()
        count = 0
        first = True
        extra_counts = defaultdict(int)
        new_objects = []
        for row in csv_reader:
            if first:
                # Read the columns
                columns = row
                if columns[0].startswith(CSV_BOM):
                    columns[0] = columns[0][len(CSV_BOM):]
                first = False
                continue

            if filter_func and not filter_func(zip(columns, row)):
                continue

            if not row:
                continue

            # Read a data row
            fields = dict()
            point_coords = [None, None]
            ukey_values = {}
            if cls._rel_to_feed == 'feed':
                fields['feed'] = feed
            for column_name, value in zip(columns, row):
                if column_name not in name_map:
                    val = null_convert(value)
                    if val is not None:
                        fields.setdefault('extra_data', {})[column_name] = val
                        extra_counts[column_name] += 1
                elif column_name in val_map:
                    fields[name_map[column_name]] = val_map[column_name](value)
                else:
                    assert column_name in point_map
                    pos, converter = point_map[column_name]
                    point_coords[pos] = converter(value)

                # Is it part of the unique key?
                if column_name in cls._unique_fields:
                    ukey_values[column_name] = value

            # Join the lat/long into a point
            if point_map:
                assert point_coords[0] and point_coords[1]
                fields['point'] = "POINT(%s)" % (' '.join(point_coords))

            # Is the item unique?
            ukey = tuple(ukey_values.get(u) for u in cls._unique_fields)
            if ukey in unique_line:
                logger.warning(
                    '%s line %d is a duplicate of line %d, not imported.',
                    cls._filename, csv_reader.line_num, unique_line[ukey])
                continue
            else:
                unique_line[ukey] = csv_reader.line_num

            # TODO: geo
            if 'point' in fields:
                del fields['point']

            # Create after accumulating a batch
            new_objects.append(cls(**fields))
            if len(new_objects) % batch_size == 0:  # pragma: no cover
                cls.objects.bulk_create(new_objects)
                count += len(new_objects)
                logger.info(
                    "Imported %d %s",
                    count, cls._meta.verbose_name_plural)
                new_objects = []

        # Create remaining objects
        if new_objects:
            cls.objects.bulk_create(new_objects)

        # Take note of extra fields
        if extra_counts:
            extra_columns = feed.meta.setdefault(
                'extra_columns', {}).setdefault(cls.__name__, [])
            for column in columns:
                if column in extra_counts and column not in extra_columns:
                    extra_columns.append(column)
            feed.save()
        return len(unique_line)