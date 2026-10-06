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

  const box = messages();
  if (box) box.scrollIntoView({ block: "end" });
  schedule();
})();
