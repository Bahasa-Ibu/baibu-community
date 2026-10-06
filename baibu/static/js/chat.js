// Sends messages and fetches replies without reloading the page. Without
// JavaScript the forms post normally and the page reloads.
(function () {
  "use strict";
  const POLL_MS = 1500;
  let timer = null;

  function messages() {
    return document.getElementById("chat-messages");
  }

  function replace(html) {
    const current = messages();
    const template = document.createElement("template");
    template.innerHTML = html.trim();
    const next = template.content.firstElementChild;
    if (current && next) {
      current.replaceWith(next);
      next.scrollIntoView({ block: "end" });
    }
    schedule();
  }

  function setKey(response) {
    const key = response.headers.get("X-Chat-Next-Key");
    const input = document.querySelector("[data-chat-composer] input[name=idempotency_key]");
    if (key && input) input.value = key;
  }

  function schedule() {
    clearTimeout(timer);
    const box = messages();
    if (box && box.dataset.pending === "true") {
      timer = setTimeout(poll, POLL_MS);
    }
  }

  async function poll() {
    const box = messages();
    if (!box) return;
    try {
      const response = await fetch(box.dataset.url, { headers: { "X-Requested-With": "fetch" } });
      if (response.ok) replace(await response.text());
      else schedule();
    } catch (error) {
      schedule();
    }
  }

  async function submit(form, event) {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    if (button) button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "fetch" },
      });
      replace(await response.text());
      if (response.ok && form.matches("[data-chat-composer]")) {
        form.reset();
        setKey(response);
      }
    } catch (error) {
      form.submit();
    } finally {
      if (button) button.disabled = false;
    }
  }

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (form.matches("[data-chat-composer]") && messages()) submit(form, event);
    else if (form.matches("[data-chat-action]")) submit(form, event);
  });

  document.addEventListener("keydown", function (event) {
    const target = event.target;
    if (event.key === "Enter" && !event.shiftKey && target.closest && target.closest("[data-chat-composer]")) {
      event.preventDefault();
      target.form.requestSubmit();
    }
  });

  // Voice messages: record with MediaRecorder and upload. The button stays
  // hidden where the browser cannot record or voice input is off.
  const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  const recorder = { media: null, chunks: [], timer: null };

  function voiceStatus(text) {
    const status = document.querySelector("[data-voice-status]");
    if (status) status.textContent = text || "";
  }

  function setRecording(button, on) {
    button.setAttribute("aria-pressed", on ? "true" : "false");
    button.textContent = on ? button.dataset.labelStop : button.dataset.labelStart;
  }

  async function upload(button, blob, type) {
    const form = button.closest("form");
    const data = new FormData();
    data.append("csrfmiddlewaretoken", form.querySelector("input[name=csrfmiddlewaretoken]").value);
    data.append("idempotency_key", form.querySelector("input[name=idempotency_key]").value);
    data.append("audio", blob, "voice." + (type.split("/")[1] || "webm").split(";")[0]);
    button.disabled = true;
    button.textContent = button.dataset.labelSending;
    try {
      const response = await fetch(button.dataset.url, {
        method: "POST",
        body: data,
        headers: { "X-Requested-With": "fetch" },
      });
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      if (messages() && (response.headers.get("Content-Type") || "").startsWith("text/html")) {
        replace(await response.text());
        if (response.ok) setKey(response);
        voiceStatus("");
      } else {
        voiceStatus(response.ok ? "" : (await response.text()) || button.dataset.labelFailed);
      }
    } catch (error) {
      voiceStatus(button.dataset.labelFailed);
    } finally {
      button.disabled = false;
      setRecording(button, false);
    }
  }

  async function startRecording(button) {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      voiceStatus(button.dataset.labelDenied);
      return;
    }
    const type = TYPES.find(function (t) { return MediaRecorder.isTypeSupported(t); }) || "";
    const media = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    recorder.media = media;
    recorder.chunks = [];
    media.addEventListener("dataavailable", function (event) {
      if (event.data.size) recorder.chunks.push(event.data);
    });
    media.addEventListener("stop", function () {
      clearTimeout(recorder.timer);
      stream.getTracks().forEach(function (track) { track.stop(); });
      const mime = (media.mimeType || type || "audio/webm").split(";")[0];
      const blob = new Blob(recorder.chunks, { type: mime });
      recorder.media = null;
      if (blob.size) upload(button, blob, mime);
      else setRecording(button, false);
    });
    media.start();
    voiceStatus("");
    setRecording(button, true);
    const limit = parseInt(button.dataset.maxSeconds, 10) || 120;
    recorder.timer = setTimeout(function () {
      if (media.state === "recording") media.stop();
    }, limit * 1000);
  }

  const voiceButton = document.querySelector("[data-voice-record]");
  if (voiceButton && window.MediaRecorder && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    voiceButton.hidden = false;
    voiceButton.addEventListener("click", function () {
      if (recorder.media && recorder.media.state === "recording") recorder.media.stop();
      else if (!voiceButton.disabled) startRecording(voiceButton);
    });
  }

  const box = messages();
  if (box) box.scrollIntoView({ block: "end" });
  schedule();
})();
