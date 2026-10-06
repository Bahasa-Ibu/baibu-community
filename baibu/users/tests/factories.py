"""Test data factories. All data is synthetic; never use real people's details."""

import factory
from factory.django import DjangoModelFactory

from baibu.users.models import ConsentRecord
from baibu.users.models import User


class UserFactory(DjangoModelFactory):
    email = factory.Sequence(lambda n: f"person{n}@example.org")
    name = factory.Sequence(lambda n: f"Test Person {n}")
    city = "Testville"
    country = "Exampleland"
    password = factory.django.Password("correct-horse-battery-staple")

    class Meta:
        model = User
        django_get_or_create = ["email"]


class ConsentRecordFactory(DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    tier = ConsentRecord.Tier.TRAINING_ELIGIBLE
    source = "test"
    scope = "platform"

    class Meta:
        model = ConsentRecord
