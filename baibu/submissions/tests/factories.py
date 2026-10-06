"""Synthetic submissions. Texts are invented for the tests."""

import factory
from factory.django import DjangoModelFactory

from baibu.core import storage
from baibu.submissions import text as text_rules
from baibu.submissions.models import Submission
from baibu.users.models import ConsentRecord
from baibu.users.tests.factories import UserFactory

SAMPLE_TEXT = "The river was high that spring, so we carried the baskets along the ridge path instead."


class SubmissionFactory(DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    language_code = "en"
    consent_tier = ConsentRecord.Tier.EVAL_ONLY
    content_hash = factory.Sequence(lambda n: text_rules.content_hash(f"{SAMPLE_TEXT} {n}"))
    word_count = 16
    character_count = len(SAMPLE_TEXT)

    class Meta:
        model = Submission

    @factory.lazy_attribute
    def raw_key(self):
        return storage.save_json(f"submissions/raw/test/{self.content_hash}.json", {"text": SAMPLE_TEXT})
