from django.contrib.auth.models import User, Group
from rest_framework import viewsets
from rest_framework import permissions
from backend.serializers.user import UserSerializer
from rest_framework_extensions.mixins import NestedViewSetMixin

class UserViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]