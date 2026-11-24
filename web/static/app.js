"use strict";

/* Auto Application UI — no framework, no API calls. */
(() => {
  const storageKey = "auto-application-theme";
  const root = document.documentElement;
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  function savedTheme() {
    try {
      const saved = window.localStorage.getItem(storageKey);
      return saved === "dark" || saved === "light" ? saved : null;
    } catch {
      return null;
    }
  }

  function applyTheme(theme, persist = false) {
    root.dataset.theme = theme;
    if (persist) {
      try {
        window.localStorage.setItem(storageKey, theme);
      } catch {
        /* storage unavailable */
      }
    }

    if (themeButton) {
      const isDark = theme === "dark";
      themeButton.textContent = isDark ? "☀ LIGHT MODE" : "☾ DARK MODE";
      themeButton.setAttribute(
        "aria-label",
        isDark ? "Activate light mode" : "Activate dark mode"
      );
      themeButton.setAttribute("aria-pressed", String(isDark));
    }
  }

  const header = document.querySelector(".header");
  let themeButton = null;

  if (header) {
    const actions = document.createElement("div");
    actions.className = "header-actions";

    themeButton = document.createElement("button");
    themeButton.type = "button";
    themeButton.className = "theme-toggle";
    actions.append(themeButton);

    const badge = header.querySelector(".local");
    if (badge) actions.append(badge);
    header.append(actions);
  }

  applyTheme(savedTheme() ?? (systemDark.matches ? "dark" : "light"));

  themeButton?.addEventListener("click", () => {
    applyTheme(
      root.dataset.theme === "dark" ? "light" : "dark",
      true
    );
  });

  systemDark.addEventListener?.("change", (event) => {
    if (!savedTheme()) {
      applyTheme(event.matches ? "dark" : "light");
    }
  });

  function markSubmitting(form, text) {
    const button = form.querySelector('button[type="submit"]');
    if (!button) return;

    button.dataset.originalLabel = button.textContent;
    button.textContent = text;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }

  const generateForm = document.getElementById("generate-form");
  const generationLoader = document.getElementById("generation-loader");
  
  generateForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
  
      const button = document.getElementById("generate-button");
  
      if (button.disabled) return;
  
      // Collect the form data.
      const formData = new FormData(generateForm);
  
      // Display the loader.
      generationLoader.hidden = false;
      markSubmitting(generateForm, "GENERATING…");
  
      try {
          const response = await fetch(generateForm.action, {
              method: "POST",
              body: formData,
              credentials: "same-origin"
          });
  
          if (!response.ok) {
              throw new Error(`HTTP ${response.status}`);
          }
  
          if (!response.redirected) {
              throw new Error("Expected a redirect from the server.");
          }
  
          const destination = new URL(response.url);
  
          if (destination.origin !== window.location.origin) {
              throw new Error("Unexpected redirect destination.");
          }
  
          // The server has finished processing.
          window.location.assign(destination.href);
  
      } catch (error) {
          console.error("Generation failed:", error);
  
          generationLoader.hidden = true;
  
          button.disabled = false;
          button.removeAttribute("aria-busy");
          button.textContent =
              button.dataset.originalLabel || "Generate applications →";
  
          alert("Generation failed. Please check the server logs.");
      }
  });



  const smtpFields = [
    "host_setup",
    "port_setup",
    "sender_setup",
    "smtp_user_setup",
    "smtp_password_setup",
    "force_send"
  ];
  
  document.querySelectorAll(".send-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
  
      for (const name of smtpFields) {
        const source = document.getElementById(name);
  
        if (!source || !source.value.trim()) {
          event.preventDefault();
          alert(`Please fill in the ${name} field first.`);
          source?.focus();
          return;
        }
  
        let hidden = form.querySelector(`input[name="${name}"]`);
  
        if (!hidden) {
          hidden = document.createElement("input");
          hidden.type = "hidden";
          hidden.name = name;
          form.appendChild(hidden);
        }
  
        hidden.value = source.value;
      }
  
      markSubmitting(form, "SENDING…");
    });
  });

  /*
  document.querySelectorAll(".send-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      markSubmitting(form, "SENDING…");
    });
  });*/

  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;

    document.querySelectorAll('button[aria-busy="true"]').forEach((button) => {
      button.disabled = false;
      button.removeAttribute("aria-busy");

      if (button.dataset.originalLabel) {
        button.textContent = button.dataset.originalLabel;
      }
    });
  });

  document.querySelectorAll(".password-toggle").forEach((button) => {
      button.addEventListener("click", () => {
          const input = button.parentElement.querySelector("input");
          const visible = button.getAttribute("aria-pressed") === "true";
  
          if (input.classList.contains("masked-input")) {
              input.classList.toggle("is-visible", !visible);
          } else {
              input.type = visible ? "password" : "text";
          }
  
          button.textContent = visible ? "Show" : "Hide";
          button.setAttribute(
              "aria-label",
              visible ? "Show password" : "Hide password"
          );
          button.setAttribute("aria-pressed", String(!visible));
      });
  });

})();



