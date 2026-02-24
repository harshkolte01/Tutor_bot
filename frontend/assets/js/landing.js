import { getApiBaseUrl } from "../../components/api_client.js";
import { clearSession, getSession } from "../../components/session.js";

function applyAuthState() {
  const session = getSession();
  const userSlot = document.querySelector("[data-user-slot]");
  const guestActions = document.querySelectorAll("[data-guest-action]");
  const signOutButton = document.querySelector("[data-signout]");

  if (session?.user) {
    const displayName = session.user.username || session.user.email;
    userSlot.textContent = displayName;
    userSlot.hidden = false;
    guestActions.forEach((item) => {
      item.hidden = true;
    });
    signOutButton.hidden = false;
  } else {
    userSlot.hidden = true;
    guestActions.forEach((item) => {
      item.hidden = false;
    });
    signOutButton.hidden = true;
  }
}

function registerEvents() {
  const signOutButton = document.querySelector("[data-signout]");
  if (signOutButton) {
    signOutButton.addEventListener("click", () => {
      clearSession();
      window.location.reload();
    });
  }
}

function revealSections() {
  const items = document.querySelectorAll("[data-reveal]");
  if (!("IntersectionObserver" in window)) {
    items.forEach((item) => item.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 },
  );

  items.forEach((item, index) => {
    item.style.transitionDelay = `${index * 60}ms`;
    observer.observe(item);
  });
}

function mountApiBaseUrl() {
  const target = document.querySelector("[data-api-base-url]");
  if (target) {
    target.textContent = getApiBaseUrl();
  }
}

applyAuthState();
registerEvents();
revealSections();
mountApiBaseUrl();
