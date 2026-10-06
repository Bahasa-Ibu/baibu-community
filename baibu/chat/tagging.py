"""Optional tagging of conversations by topic, language and intent.

Off unless ``CHAT_TAGGING_ENABLED``. Topics are defined by the deployment in
the admin (*Chat → Topics*); intents come from ``CHAT_TAGGING_INTENTS``.
A Celery beat task tags conversations that have been idle for
``CHAT_TAGGING_IDLE_MINUTES`` and changed since they were last tagged, but
only conversations whose consent tier allows evaluation.

The tagger asks a language model through LiteLLM (``CHAT_TAGGING_MODEL``,
or the chat's default model) using the template
``chat/tagging_prompt.txt``. With the ``mock`` model it matches topic
labels and slugs as keywords instead, so it works without a model.
"""

import json
import logging
import re
from dataclasses import dataclass
from dataclasses import field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from baibu.users.consent import TIER_RANK

from . import llm
from .models import Conversation
from .models import ConversationTag
from .models import Message
from .models import Topic

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class TaggingError(Exception):
    pass


@dataclass
class TagResult:
    topics: list[str] = field(default_factory=list)
    language: str = ""
    intent: str = ""


def transcript(conversation: Conversation) -> str:
    lines = [
        f"{'User' if m.role == Message.Role.USER else 'Assistant'}: {m.content}"
        for m in conversation.messages.exclude(content="")[: settings.CHAT_TAGGING_MAX_MESSAGES]
    ]
    return "\n".join(lines)[: settings.CHAT_TAGGING_MAX_CHARACTERS]


def model_config() -> llm.ModelConfig:
    from .services import default_variant

    if settings.CHAT_TAGGING_MODEL:
        return llm.ModelConfig(model=settings.CHAT_TAGGING_MODEL)
    return llm.ModelConfig.from_variant(default_variant())


def keyword_tags(text: str, topics: list[Topic], language: str) -> TagResult:
    """The mock tagger: a topic matches if its slug or label appears as words."""
    lowered = text.lower()
    found = []
    for topic in topics:
        for term in {topic.slug.replace("-", " "), topic.label.lower()}:
            if re.search(rf"\b{re.escape(term.lower())}\b", lowered):
                found.append(topic.slug)
                break
    intent = "question" if "?" in text else "conversation"
    return TagResult(topics=found, language=language, intent=intent if intent in intents() else "")


def intents() -> list[str]:
    return list(settings.CHAT_TAGGING_INTENTS)


def model_tags(text: str, topics: list[Topic], config: llm.ModelConfig) -> TagResult:
    prompt = render_to_string(
        "chat/tagging_prompt.txt",
        {"topics": topics, "intents": intents(), "max_topics": settings.CHAT_TAGGING_MAX_TOPICS},
    )
    try:
        completion = llm.complete(config, [{"role": "system", "content": prompt}, {"role": "user", "content": text}])
    except llm.ModelError as exc:
        raise TaggingError(str(exc)) from exc
    match = _JSON_BLOCK.search(completion.content or "")
    try:
        data = json.loads(match.group(0) if match else completion.content)
    except (json.JSONDecodeError, TypeError) as exc:
        msg = "Tagger answer is not JSON."
        raise TaggingError(msg) from exc
    if not isinstance(data, dict):
        msg = "Tagger answer is not an object."
        raise TaggingError(msg)
    known = {topic.slug for topic in topics}
    raw_topics = data.get("topics") if isinstance(data.get("topics"), list) else []
    chosen = [slug for slug in dict.fromkeys(str(t) for t in raw_topics) if slug in known]
    intent = str(data.get("intent") or "")
    return TagResult(
        topics=chosen[: settings.CHAT_TAGGING_MAX_TOPICS],
        language=str(data.get("language") or "")[:24],
        intent=intent if intent in intents() else "",
    )


def tag_conversation(conversation: Conversation) -> ConversationTag:
    topics = list(Topic.objects.filter(active=True))
    activity = conversation.last_activity_at
    config = model_config()
    tag, _created = ConversationTag.objects.get_or_create(
        conversation=conversation, defaults={"tagged_activity_at": activity}
    )
    text = transcript(conversation)
    try:
        if config.model == "mock":
            result = keyword_tags(text, topics, conversation.language_code)
            tagger = "keywords"
        else:
            result = model_tags(text, topics, config)
            tagger = config.model
        error = ""
    except TaggingError as exc:
        result, tagger, error = TagResult(), config.model, str(exc)[:500]
        logger.warning("Could not tag conversation %s: %s", conversation.pk, error)
    with transaction.atomic():
        tag.language = result.language
        tag.intent = result.intent
        tag.tagger = tagger[:255]
        tag.error = error
        tag.tagged_activity_at = activity
        tag.save()
        tag.topics.set([t for t in topics if t.slug in result.topics])
    return tag


def eligible_tiers() -> list[str]:
    minimum = TIER_RANK[settings.CHAT_TAGGING_MIN_TIER]
    return [tier for tier, rank in TIER_RANK.items() if rank >= minimum]


def due_conversations(now=None):
    """Idle conversations with consent, never tagged or changed since tagging."""
    from django.db.models import F
    from django.db.models import Q

    now = now or timezone.now()
    idle_since = now - timedelta(minutes=settings.CHAT_TAGGING_IDLE_MINUTES)
    return (
        Conversation.objects.filter(last_activity_at__lte=idle_since, consent_tier__in=eligible_tiers())
        .filter(messages__isnull=False)
        .filter(Q(tag__isnull=True) | Q(tag__tagged_activity_at__lt=F("last_activity_at")))
        .distinct()
        .order_by("last_activity_at")
    )


def tag_due(now=None) -> int:
    if not settings.CHAT_TAGGING_ENABLED:
        return 0
    count = 0
    for conversation in due_conversations(now)[: settings.CHAT_TAGGING_BATCH_SIZE]:
        tag_conversation(conversation)
        count += 1
    return count
