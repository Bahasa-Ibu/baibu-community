import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from baibu.users.consent import consent_required
from baibu.users.consent import consent_state
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord

pytestmark = pytest.mark.django_db
Tier = ConsentRecord.Tier


def test_no_record_means_no_data_use(user):
    state = consent_state(user=user)
    assert state.latest_record is None
    assert state.tier == Tier.NONE
    assert state.allows(Tier.NONE)
    assert not state.allows(Tier.EVAL_ONLY)


def test_new_decision_revokes_previous_and_keeps_history(user):
    first = record_consent(user=user, tier=Tier.TRAINING_ELIGIBLE, source="test")
    second = record_consent(user=user, tier=Tier.EVAL_ONLY, source="test")
    first.refresh_from_db()
    assert first.revoked_at is not None
    assert second.revoked_at is None
    assert consent_state(user=user).tier == Tier.EVAL_ONLY
    assert user.consent_records.count() == 2


def test_higher_tier_allows_lower_uses(user):
    record_consent(user=user, tier=Tier.TRAINING_ELIGIBLE, source="test")
    state = consent_state(user=user)
    assert state.allows(Tier.EVAL_ONLY)
    assert state.allows(Tier.TRAINING_ELIGIBLE)


def test_scopes_are_independent(user):
    record_consent(user=user, tier=Tier.TRAINING_ELIGIBLE, source="test", scope="chat")
    assert consent_state(user=user).tier == Tier.NONE
    assert consent_state(user=user, scope="chat").tier == Tier.TRAINING_ELIGIBLE


def test_revoked_latest_record_counts_as_none(user):
    record = record_consent(user=user, tier=Tier.TRAINING_ELIGIBLE, source="test")
    ConsentRecord.objects.filter(pk=record.pk).update(revoked_at=record.granted_at)
    assert consent_state(user=user).tier == Tier.NONE


def _protected_view(request):
    return HttpResponse("ok")


def test_consent_required_redirects_without_consent(user):
    request = RequestFactory().get("/protected/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    response = consent_required(Tier.EVAL_ONLY)(_protected_view)(request)
    assert response.status_code == 302
    assert response.url == reverse("users:consent")


def test_consent_required_allows_with_consent(user):
    record_consent(user=user, tier=Tier.EVAL_ONLY, source="test")
    request = RequestFactory().get("/protected/")
    request.user = user
    response = consent_required(Tier.EVAL_ONLY)(_protected_view)(request)
    assert response.content == b"ok"


def test_consent_required_sends_anonymous_to_login():
    request = RequestFactory().get("/protected/")
    request.user = AnonymousUser()
    response = consent_required(Tier.EVAL_ONLY)(_protected_view)(request)
    assert response.status_code == 302
    assert response.url == reverse("account_login")
