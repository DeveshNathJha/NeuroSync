// View: Consent & setup. Nothing can be recorded until a consent record exists.

import { api, getActor, setActiveSession, setActor } from "../api.js";
import { errorText, h, notify, pageHeader, withBusy } from "../dom.js";

const ROLES = [
  "Parent / guardian",
  "The subject (adult, own consent)",
  "Legal representative",
  "Other",
];

function field(id, label, input, hint) {
  const hintId = hint ? `${id}-hint` : null;
  if (hintId) input.setAttribute("aria-describedby", hintId);
  return h("div", { class: "field" },
    h("label", { for: id }, label),
    input,
    hint ? h("p", { class: "hint", id: hintId }, hint) : null);
}

export function render(root, ctx) {
  const maxMin = ctx.config?.max_duration_min ?? 90;

  const subject = h("input", {
    id: "subject-id", name: "subject_id", required: true, autocomplete: "off", maxlength: 64,
    placeholder: "e.g. S-014",
  });
  const role = h("select", { id: "given-by", name: "given_by", required: true },
    ROLES.map((r) => h("option", { value: r }, r)));
  const roleOther = h("input", { id: "given-by-other", name: "given_by_other", maxlength: 80 });
  const roleOtherField = field("given-by-other", "Describe the role", roleOther);
  roleOtherField.hidden = true;
  role.addEventListener("change", () => {
    roleOtherField.hidden = role.value !== "Other";
    roleOther.required = role.value === "Other";
  });

  const recordedBy = h("input", {
    id: "recorded-by", name: "recorded_by", required: true, maxlength: 80, autocomplete: "name",
    value: getActor(),
  });
  const purpose = h("input", {
    id: "purpose", name: "purpose", maxlength: 160, value: "Session observation notes",
  });
  const consentBox = h("input", { id: "consent-ok", type: "checkbox", required: true });
  const videoBox = h("input", { id: "video-stored", type: "checkbox" });
  const modeLive = h("input", { type: "radio", name: "mode", id: "mode-live", value: "live", checked: true });
  const modeVideo = h("input", { type: "radio", name: "mode", id: "mode-video", value: "video" });

  const formError = h("p", { class: "form-error", role: "alert", hidden: true });
  const submit = h("button", { type: "submit", class: "btn btn-primary" }, "Create session");
  const warningsBox = h("div", { class: "panel panel-warn", hidden: true, role: "alert" });

  const form = h("form", { class: "panel form", novalidate: true },
    h("h2", {}, "Consent record"),
    field("subject-id", "Subject id (pseudonym)", subject,
      "Use a code, never a name, e-mail address or phone number."),
    field("given-by", "Consent given by", role),
    roleOtherField,
    field("recorded-by", "Recorded by (your name or role)", recordedBy,
      "Stored with each action in the audit log."),
    field("purpose", "Purpose", purpose),
    h("div", { class: "check" }, consentBox,
      h("label", { for: "consent-ok" },
        "I confirm that informed consent for this session was obtained and recorded.")),
    h("div", { class: "check" }, videoBox,
      h("label", { for: "video-stored" },
        "Consent also covers storing the raw video (off by default; without it uploaded videos are deleted after analysis).")),
    h("fieldset", { class: "modes" },
      h("legend", {}, "Session type"),
      h("div", { class: "radio" }, modeLive, h("label", { for: "mode-live" }, "Live webcam session")),
      h("div", { class: "radio" }, modeVideo, h("label", { for: "mode-video" }, "Analyse a recorded video"))),
    formError,
    h("div", { class: "actions" }, submit));

  function showError(text) {
    formError.textContent = text;
    formError.hidden = !text;
  }

  function goTo(id, mode) {
    ctx.navigate(mode === "video" ? `#/video/${encodeURIComponent(id)}` : `#/live/${encodeURIComponent(id)}`);
  }

  function showWarnings(id, mode, warnings) {
    warningsBox.replaceChildren(
      h("h2", {}, "Please check the subject id"),
      h("ul", {}, warnings.map((w) => h("li", {}, w))),
      h("p", {}, "Subject ids should be pseudonyms. Continue only if this id cannot identify the person."),
      h("div", { class: "actions" },
        h("button", { type: "button", class: "btn btn-primary", onclick: () => goTo(id, mode) }, "Continue anyway"),
        h("button", {
          type: "button", class: "btn",
          onclick: async (e) => {
            await withBusy(e.currentTarget, "Discarding…", async () => {
              try {
                await api.discard(id);
              } catch (err) {
                notify(errorText(err), "error");
              }
              setActiveSession(null);
              warningsBox.hidden = true;
              subject.focus();
            });
          },
        }, "Discard and change the id")));
    warningsBox.hidden = false;
    warningsBox.querySelector("button").focus();
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("");
    const givenBy = role.value === "Other" ? roleOther.value.trim() : role.value;
    if (!subject.value.trim()) return showError("Enter a subject id.");
    if (!givenBy) return showError("Describe who gave consent.");
    if (!recordedBy.value.trim()) return showError("Enter who is recording this session.");
    if (!consentBox.checked) return showError("A session can only be created after consent was obtained.");
    const mode = modeVideo.checked ? "video" : "live";

    await withBusy(submit, "Creating…", async () => {
      try {
        setActor(recordedBy.value.trim());
        const res = await api.createSession({
          mode,
          consent: {
            subject_id: subject.value.trim(),
            given_by: givenBy,
            recorded_by: recordedBy.value.trim(),
            purpose: purpose.value.trim() || "Session observation notes",
            video_stored: videoBox.checked,
          },
          consent_confirmed: consentBox.checked,
        });
        setActiveSession({ id: res.session_id, mode });
        ctx.refreshStatus?.();
        const warnings = Array.isArray(res.warnings) ? res.warnings : [];
        if (warnings.length) showWarnings(res.session_id, mode, warnings);
        else goTo(res.session_id, mode);
      } catch (err) {
        showError(errorText(err));
      }
    });
  });

  root.append(
    pageHeader("Consent & setup", "Every session starts with a consent record."),
    h("p", { class: "lead" },
      `A session records observable events (movement patterns, loud sounds and heart rate from the webcam) `
      + `as suggestions for you to confirm or reject afterwards. A session always has an end: you stop it, `
      + `or it stops automatically after ${maxMin} minutes. Nothing runs in the background.`),
    warningsBox,
    form);
}
