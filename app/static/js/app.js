/* UWU — клиентская логика: модальные окна, живой поиск, плавающий чат. */
(function () {
  "use strict";

  /* ---------- Модальные окна ---------- */
  function openModal(id) {
    var el = document.getElementById(id);
    if (el) {
      el.classList.add("open");
      var first = el.querySelector("input, select, textarea");
      if (first) setTimeout(function () { first.focus(); }, 80);
    }
  }

  function closeModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.remove("open");
  }

  function closeAllModals() {
    document.querySelectorAll(".modal-backdrop.open").forEach(function (m) {
      m.classList.remove("open");
    });
  }

  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-modal-open]");
    if (opener) {
      openModal(opener.getAttribute("data-modal-open"));
      return;
    }
    var closer = e.target.closest("[data-modal-close]");
    if (closer) {
      var backdrop = closer.closest(".modal-backdrop");
      if (backdrop) closeModal(backdrop.id);
      return;
    }
    // Клик по подложке (не по окну) закрывает модалку.
    if (e.target.classList && e.target.classList.contains("modal-backdrop")) {
      closeModal(e.target.id);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeAllModals();
  });

  /* ---------- Живой поиск по таблицам ---------- */
  function initSearch(input) {
    var selector = input.getAttribute("data-search");
    if (!selector) return;
    var table = document.querySelector(selector);
    if (!table) return;

    var rows = Array.prototype.slice.call(
      table.querySelectorAll("tbody tr[data-row]")
    );

    input.addEventListener("input", function () {
      var q = input.value.toLowerCase().trim();
      var visible = 0;
      rows.forEach(function (row) {
        var text = row.textContent.toLowerCase();
        var match = text.indexOf(q) !== -1;
        row.style.display = match ? "" : "none";
        if (match) visible++;
      });

      // Показ «ничего не найдено».
      var empty = table.querySelector("tbody tr[data-empty]");
      if (empty) {
        empty.style.display = visible === 0 ? "" : "none";
      }
    });
  }

  document.querySelectorAll("input[data-search]").forEach(initSearch);

  /* ---------- Плавающий чат (заглушка мессенджера) ---------- */
  var fab = document.getElementById("chat-fab");
  var popup = document.getElementById("chat-popup");
  var chatClose = document.getElementById("chat-close");
  var chatSend = document.getElementById("chat-send");
  var chatInput = document.getElementById("chat-input");
  var chatMessages = document.getElementById("chat-messages");

  function toggleChat(open) {
    if (!popup) return;
    var shouldOpen = open !== undefined ? open : !popup.classList.contains("open");
    if (shouldOpen) {
      popup.classList.add("open");
      if (chatInput) setTimeout(function () { chatInput.focus(); }, 120);
    } else {
      popup.classList.remove("open");
    }
  }

  if (fab) fab.addEventListener("click", function () { toggleChat(); });
  if (chatClose) chatClose.addEventListener("click", function () { toggleChat(false); });

  function addMessage(text, kind) {
    if (!chatMessages) return;
    var el = document.createElement("div");
    el.className = "msg " + (kind || "incoming");
    var now = new Date();
    var time = now.getHours() + ":" + String(now.getMinutes()).padStart(2, "0");
    el.innerHTML = '<span>' + escapeHtml(text) + '</span><span class="time">' + time + "</span>";
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function send() {
    if (!chatInput || !chatInput.value.trim()) return;
    addMessage(chatInput.value.trim(), "outgoing");
    chatInput.value = "";
    // Заглушка ответа (пока мессенджер не подключён к реальному бэкенду).
    setTimeout(function () {
      addMessage("Сообщение получено. Мессенджер находится в разработке.", "incoming");
    }, 600);
  }

  if (chatSend) chatSend.addEventListener("click", send);
  if (chatInput) {
    chatInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") send();
    });
  }
})();
