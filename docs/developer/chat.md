# Assistant chat

Signed-in users can talk with an assistant at `/chat/`. Replies come from a
language model the deployment chooses, reached through
[LiteLLM](https://docs.litellm.ai/). The project does not recommend a
model. Out of the box the assistant uses the built-in `mock` model, which
echoes messages back without any network call, so a new installation works
before a model is configured.

## Consent

Before their first conversation, users choose how their conversations may
be used (`none`, `eval_only` or `training_eligible`), recorded under the
consent scope `CHAT_CONSENT_SCOPE` (default `chat`), separately from the
consent for submissions. Any choice, including `none`, lets them chat: the
conversation is still stored so they can return to it. Each conversation
records the tier in force when it started. Users can delete a conversation
at any time.

## How a reply is produced

```mermaid
sequenceDiagram
    actor User
    participant Web as Django
    participant DB as PostgreSQL
    participant Worker as Celery worker
    participant Model as Model (via LiteLLM)
    User->>Web: message + idempotency key
    Web->>DB: Message (user) + Run (queued) + events
    Web-->>Worker: execute_run (after commit)
    Worker->>DB: claim run (queued → running)
    Worker->>Model: system prompt + recent messages
    Model-->>Worker: reply
    Worker->>DB: Message (assistant), Run completed, event
    User->>Web: poll /chat/<id>/messages/
```

- **Idempotent sends.** Each composer form carries a random key. Sending the
  same key twice (a double click, a retried request) returns the first
  message and run instead of creating new ones.
- **One reply at a time.** While a conversation has a queued or running run,
  further sends are refused with a message asking the user to wait.
- **Runs.** A run is one attempt to reply to one user message. The worker
  claims it with a conditional update, so a run is never executed twice.
  The run records the model and prompt version used, token usage, latency
  and, on failure, an error code.
- **Retries.** A failed reply shows *Try again*. A retry creates a new run
  for the same message (the message is not duplicated), up to
  `CHAT_MAX_ATTEMPTS` attempts per message.
- **Recovery.** Every minute, Celery beat runs `sweep_runs`: runs still
  running after `CHAT_RUN_TIMEOUT_SECONDS` are failed (so the user can
  retry), queued runs whose task was lost are sent again, and queued runs
  that never started within three timeouts are failed. A reply that arrives
  after its run was failed is discarded.
- **Context.** The model receives the system prompt and the last
  `CHAT_CONTEXT_MESSAGES` messages up to the one being answered.
- **Audit trail.** Every step is a `ConversationEvent` (conversation
  started, message sent, run queued, started, completed, failed, retried).
  Events are append-only.

The page works without JavaScript (forms post and the page reloads). With
JavaScript, `static/js/chat.js` sends in the background and polls for the
reply.

## Reports

Under each assistant reply, *Report* lets the user say what is wrong
(harmful, wrong or misleading, something else) with an optional note.
Reports go to the staff queue described in [Staff review](staff.md); each
user can report a reply once.

## Topic tagging

Tagging labels conversations with **topics**, the **language** the person
writes in and their **intent**, for statistics and review. It is **off by
default** (`CHAT_TAGGING_ENABLED`).

- **Topics** are defined by the deployment in the admin (*Chat → Topics*):
  a code, a label and an optional description that helps the tagger.
  Inactive topics are not offered.
- **Intents** come from `CHAT_TAGGING_INTENTS` (default `question`,
  `advice`, `information`, `conversation`, `other`).
- **When.** Every 10 minutes (`CHAT_TAGGING_INTERVAL_SECONDS`) a beat task
  tags up to `CHAT_TAGGING_BATCH_SIZE` conversations that have been idle for
  `CHAT_TAGGING_IDLE_MINUTES` and changed since they were last tagged. A
  conversation has one current tagging, replaced when it is tagged again.
- **Consent.** Only conversations whose chat consent tier is at least
  `CHAT_TAGGING_MIN_TIER` (default `eval_only`) are tagged.
- **Tagger.** The model in `CHAT_TAGGING_MODEL`, or the chat's default
  model, through LiteLLM, with the template `chat/tagging_prompt.txt`
  (overridable). It sees the first `CHAT_TAGGING_MAX_MESSAGES` messages, up
  to `CHAT_TAGGING_MAX_CHARACTERS`, and must answer with JSON; codes not in
  the lists are ignored. With the `mock` model, topics are matched as
  keywords (their label or code appearing in the conversation) and a
  question mark makes the intent `question`.
- **Failures** are recorded on the tagging (`error`) and retried only after
  the conversation changes.
- Staff see the tags on the conversation in the admin and can filter
  conversations by topic and intent.

## Models

Staff manage **model variants** in the admin (*Chat → Model variants*).
A variant has a LiteLLM model name, an optional endpoint (`api_base`) and
the **name of an environment variable** that holds the API key: keys are
never stored in the database. Extra parameters (for example
`{"temperature": 0.7}`) are passed on every call. The variant marked
*default* answers new messages; without one, `CHAT_MODEL` is used.

For a self-hosted server that speaks the OpenAI-compatible API, for example:

| Field | Value |
| --- | --- |
| Model | `openai/<model name on your server>` |
| API base | `http://llm.internal:8080/v1` |
| API key env | `LLM_API_KEY` (set in the environment of the worker) |

## Prompts

The system prompt is a Django template. Without an active prompt the
built-in template `chat/system_prompt.txt` is used (a deployment can
override it under `DEPLOYMENT_DIR/templates/`). Staff can also write prompts
in the admin (*Chat → Prompts*):

- Adding a prompt with the name `system` creates the next **version**.
  Versions cannot be edited after they are saved, so every run's
  `prompt_version` points at exactly the text that was used.
- One version per name is **active**. Tick *active* when adding, or use the
  *Make the selected version active* action to switch (or roll back).
- Templates can use `platform` (name, tagline and so on), `user_name`,
  `language_code` and `language_name`.

## Tools: web search

The assistant can call **tools** while it writes a reply. The project ships
one, `internet_search`, offered to the model only when a search provider is
configured:

1. The model asks for `internet_search` with a query.
2. The configured provider returns results (title, link, snippet).
3. The model receives them as JSON and writes its answer; the links are
   listed as **Sources** under the reply.

The model may call tools for up to `CHAT_MAX_TOOL_ROUNDS` rounds; the last
call offers no tools, so it has to answer. A failing search does not fail
the reply: the model is told the search failed. Every call is recorded as a
`ToolInvocation` (tool, provider, arguments, number of results, error,
latency) and as a `tool_completed` or `tool_failed` event. Only `http` and
`https` links are shown.

**No search provider is bundled.** To use one, write a subclass of
`baibu.chat.search.SearchProvider`:

```python
from baibu.chat.search import SearchError, SearchProvider, SearchResult


class MySearchProvider(SearchProvider):
    name = "my-search"

    def search(self, query, *, max_results):
        try:
            hits = call_my_search_service(query, limit=max_results)
        except MyServiceError as exc:
            raise SearchError("Search is unavailable.") from exc
        return [SearchResult(title=h["title"], url=h["url"], snippet=h["text"]) for h in hits]
```

and set `CHAT_SEARCH_PROVIDER=myproject.search.MySearchProvider`. Keep the
service's credentials in environment variables. For development,
`baibu.chat.search.MockSearchProvider` returns made-up `example.org`
results (a query containing `[search-fail]` fails; `[search-empty]` finds
nothing).

## Voice messages

Users can speak a message instead of typing it. Voice input is **off** until
`CHAT_STT_PROVIDER` names a speech-to-text provider; while it is off there is
no microphone button and the voice endpoints return 404.

```mermaid
sequenceDiagram
    actor User
    participant Web as Django
    participant Store as Private storage
    participant Worker as Celery worker
    participant STT as Speech to text
    User->>Web: recording + idempotency key
    Web->>Store: audio (chat/audio/yyyy/mm/dd/<id>.<ext>)
    Web->>Web: Message (empty) + AudioClip (pending) + event
    Web-->>Worker: transcribe_audio (after commit)
    Worker->>STT: audio
    STT-->>Worker: transcript
    Worker->>Web: transcript becomes the message; Run queued
    Worker-->>Worker: execute_run, as for a typed message
```

- **Recording.** `static/js/chat.js` records with the browser's
  `MediaRecorder` and shows the *Record* button only where recording is
  supported. A second click stops and sends; recording also stops after
  `CHAT_VOICE_MAX_SECONDS`. On the start page a recording starts a new
  conversation. Without JavaScript there is no voice input.
- **Upload checks.** The server accepts recordings up to
  `CHAT_VOICE_MAX_BYTES` in a format listed in `CHAT_VOICE_CONTENT_TYPES`.
  Sends are idempotent like typed ones: the same key twice stores one
  recording and creates one message.
- **Storage.** The recording goes to private storage through
  `baibu.core.storage`; an `AudioClip` keeps its key, format, size, status,
  attempt number, provider, duration and any error. Deleting the message,
  the conversation or the account deletes the recording once the deletion is
  committed.
- **Transcription.** A Celery task claims the clip (`pending` →
  `transcribing`) and sends the audio to the provider. On success the
  transcript (whitespace collapsed, cut to `CHAT_MAX_MESSAGE_CHARACTERS`)
  becomes the user message and the reply is queued exactly as for a typed
  message. The bubble shows the transcript with a *Voice message* label, and
  the user can play back their own recording (served from private storage
  after an ownership check, never cached).
- **One thing at a time.** While a recording is being transcribed the
  conversation is busy: typed and voice sends, and retries, are refused as
  they are while a reply is written.
- **Failures.** If transcription fails (provider error, no speech
  recognised, recording missing) the message says so; the user can *Try
  again* (up to `CHAT_MAX_ATTEMPTS` attempts) or type instead. Failed voice
  messages are left out of the model's context. Beat runs
  `sweep_transcriptions` every minute: transcriptions still running after
  `CHAT_RUN_TIMEOUT_SECONDS` are failed, lost tasks are sent again, and
  clips never started within three timeouts are failed.
- **Audit trail.** `audio_received`, `transcription_completed`,
  `transcription_failed` and `transcription_retried` events; the
  `message_sent` event records `via: voice`. Recordings are covered by the
  conversation's consent tier like the rest of the conversation.

### Speech-to-text providers

A provider is a subclass of `baibu.chat.speech.SpeechToText` with one
method, `transcribe(audio, *, content_type, language_code)`, returning a
`Transcript(text, language, duration, provider)` or raising
`TranscriptionError`. `language_code` is the conversation's interface
language, which may differ from the language spoken. Two are included:

- **`LiteLLMSpeechToText`** calls `litellm.transcription`, so it works with
  any transcription model LiteLLM supports, including a self-hosted server
  that speaks the OpenAI-compatible transcription API. The project does not
  recommend a model. For example:

    | Setting | Value |
    | --- | --- |
    | `CHAT_STT_PROVIDER` | `baibu.chat.speech.LiteLLMSpeechToText` |
    | `CHAT_STT_MODEL` | `openai/<model name on your server>` |
    | `CHAT_STT_API_BASE` | `http://stt.internal:8000/v1` |
    | `CHAT_STT_API_KEY_ENV` | `STT_API_KEY` (set in the worker's environment) |
    | `CHAT_STT_PARAMETERS` | `{"language": "sw"}` to fix the spoken language, if the model accepts it |

- **`MockSpeechToText`** needs no model. It transcribes every recording as
  "This is a mock transcript.", except that audio containing
  `[say:<text>]` is transcribed as `<text>`, `[stt-empty]` gives an empty
  transcript and `[stt-fail]` fails. Use it for development and tests only.

To use another service, subclass `SpeechToText` the same way as a search
provider and name it in `CHAT_STT_PROVIDER`.

## The mock model

`mock` is for development and tests:

- it replies `You said: <message>`;
- a message containing `[mock-fail]` makes the call fail;
- `[mock-tool <name>] <text>` asks for tool `<name>` with the query
  `<text>`, if the tool is available.
