"""Synthetic chat data. Messages are invented for the tests."""

import factory
from factory.django import DjangoModelFactory

from baibu.chat.models import Conversation
from baibu.chat.models import Message
from baibu.users.models import ConsentRecord
from baibu.users.tests.factories import UserFactory


class ConversationFactory(DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    consent_tier = ConsentRecord.Tier.EVAL_ONLY
    language_code = "en"

    class Meta:
        model = Conversation


class MessageFactory(DjangoModelFactory):
    conversation = factory.SubFactory(ConversationFactory)
    role = Message.Role.USER
    content = factory.Sequence(lambda n: f"Test message number {n}")

    class Meta:
        model = Message
