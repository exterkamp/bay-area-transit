from django.contrib.auth import get_user_model


def run():
    # see ref. below
    UserModel = get_user_model()

    if not UserModel.objects.filter(username='root').exists():
        user=UserModel.objects.create_user('root', password='1234')
        user.is_superuser=True
        user.is_staff=True
        user.save()
        print('Created user: root')