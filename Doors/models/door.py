from django.db import models
from django.utils.functional import classproperty


class Door(models.Model):
    '''
    The registry of Library door switches being tracked.
    '''
    tuya_device_id = models.CharField('Tuya Device ID', max_length=64)
    contents = models.CharField('Description of contents', max_length=256)

    # Related foreign keys
    # openings = OneToManyField(Opening, related_name='door') # Implicit by ForeignKey in Opening
    # events = OneToManyField(Event, related_name='door') # Implicit by ForeignKey in Event

    @classproperty
    def ids(cls):
        return sorted([door.id for door in Door.objects.all()])
