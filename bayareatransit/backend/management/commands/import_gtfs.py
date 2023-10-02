from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from backend.models.feed import Feed

class Command(BaseCommand):
    help = "Import a GTFS feed"

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('gtfs_feed',
                            metavar='<gtfsfeed.zip or folder>',
                            type=str)

        # Named (optional) arguments
        parser.add_argument('-n', '--name',
                            type=str,
                            dest='name',
                            help=(
                                'Set the name of the imported feed.  Defaults'
                                ' to name derived from agency name and'
                                ' start date'))

    def handle(self, *args, **options):
        gtfs_feed = options.get('gtfs_feed')
        unset_name = 'Imported at %s' % datetime.now()
        name = options.get('name') or unset_name

        feed = Feed.objects.create(name=name)
        feed.import_gtfs(gtfs_feed)

                # Set name based on feed
        # if feed.name == unset_name:
            # try:
            #     agency = feed.agency_set.order_by('id')[:1].get()
            # except Agency.DoesNotExist:
            #     agency = None
            # try:
            #     service = feed.service_set.order_by('id')[:1].get()
            # except Service.DoesNotExist:
            #     service = None

            # if agency:
                # name = agency.name
                # if service:
                #     name += service.start_date.strftime(' starting %Y-%m-%d')
                # else:
                #     name += ' i' + unset_name[1:]
                # feed.name = name
                # feed.save()


        self.stdout.write("Successfully imported Feed %s\n" % (feed))
