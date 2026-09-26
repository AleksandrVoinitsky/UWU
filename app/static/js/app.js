/* UWU — клиентская логика: модальные окна, живой поиск, плавающий чат. */
(function () {
  "use strict";

  /* ---------- Анимированные счётчики (data-counter) ---------- */
  function animateCounters(root) {
    var els = (root || document).querySelectorAll("[data-counter]");
    els.forEach(function (el) {
      var target = parseFloat(el.getAttribute("data-counter")) || 0;
      var decimals = parseInt(el.getAttribute("data-counter-decimals") || "0", 10);
      var prefix = el.getAttribute("data-counter-prefix") || "";
      var duration = 900;
      var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduced) { el.textContent = prefix + fmtNum(target, decimals); return; }
      var start = null;
      function step(ts) {
        if (!start) start = ts;
        var p = Math.min((ts - start) / duration, 1);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = prefix + fmtNum(target * eased, decimals);
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }

  function fmtNum(n, decimals) {
    return n.toLocaleString("ru-RU", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  window.animateCounters = animateCounters;

  /* ---------- Спарклайны (data-values) ---------- */
  function renderSparklines(root) {
    var els = (root || document).querySelectorAll(".sparkline[data-values]");
    els.forEach(function (el) {
      var values;
      try { values = JSON.parse(el.getAttribute("data-values")); } catch (e) { return; }
      if (!Array.isArray(values) || values.length < 2) return;
      var w = 140, h = 36, pad = 2;
      var min = Math.min.apply(null, values), max = Math.max.apply(null, values);
      var range = (max - min) || 1;
      function px(i) { return pad + (i / (values.length - 1)) * (w - pad * 2); }
      function py(v) { return h - pad - ((v - min) / range) * (h - pad * 2); }
      var pts = values.map(function (v, i) { return px(i).toFixed(1) + "," + py(v).toFixed(1); }).join(" ");
      var color = el.getAttribute("data-color") || "var(--accent)";
      var NS = "http://www.w3.org/2000/svg";
      var svg = document.createElementNS(NS, "svg");
      svg.setAttribute("viewBox", "0 0 " + w + " " + h);
      svg.setAttribute("preserveAspectRatio", "none");
      svg.classList.add("sparkline-svg");
      var area = document.createElementNS(NS, "polygon");
      area.setAttribute("points", (pad + "," + (h - pad)) + " " + pts + " " + ((w - pad) + "," + (h - pad)));
      area.setAttribute("fill", color);
      area.setAttribute("opacity", "0.16");
      var line = document.createElementNS(NS, "polyline");
      line.setAttribute("points", pts);
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", color);
      line.setAttribute("stroke-width", "2");
      line.setAttribute("stroke-linecap", "round");
      line.setAttribute("stroke-linejoin", "round");
      svg.appendChild(area);
      svg.appendChild(line);
      el.appendChild(svg);
    });
  }
  window.renderSparklines = renderSparklines;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { animateCounters(); renderSparklines(); });
  } else {
    animateCounters();
    renderSparklines();
  }

  /* ---------- Переключение темы (light / dark) ---------- */
  var themeToggle = document.getElementById("theme-toggle");

  function currentTheme() {
    // Без явного атрибута тема — тёмная (по умолчанию).
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("uwu-theme", theme); } catch (e) {}
    document.documentElement.dispatchEvent(
      new CustomEvent("themechange", { detail: { theme: theme } })
    );
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      applyTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  }

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

  /* ---------- Стилизованные диалоги (уведомления и подтверждения) ---------- */
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function _dialog(html) {
    var backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = html;
    document.body.appendChild(backdrop);
    requestAnimationFrame(function () { backdrop.classList.add("open"); });
    return backdrop;
  }

  function confirmDialog(message, opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      var backdrop = _dialog(
        '<div class="modal" style="max-width:380px">' +
        '<div class="modal-header"><h3>' + escapeHtml(opts.title || "Подтверждение") + '</h3></div>' +
        '<div class="modal-body">' + escapeHtml(message) + '</div>' +
        '<div class="modal-body" style="padding-top:0;display:flex;gap:10px;justify-content:flex-end">' +
        '<button type="button" class="btn secondary" data-dlg-cancel>' + escapeHtml(opts.cancelText || "Отмена") + '</button>' +
        '<button type="button" class="btn ' + (opts.danger ? "danger" : "primary") + '" data-dlg-ok>' + escapeHtml(opts.okText || "Подтвердить") + '</button>' +
        '</div></div>'
      );
      function done(val) { backdrop.remove(); resolve(val); }
      backdrop.querySelector("[data-dlg-ok]").addEventListener("click", function () { done(true); });
      backdrop.querySelector("[data-dlg-cancel]").addEventListener("click", function () { done(false); });
      backdrop.addEventListener("click", function (e) { if (e.target === backdrop) done(false); });
      var esc = function (e) {
        if (e.key === "Escape") { document.removeEventListener("keydown", esc); done(false); }
      };
      document.addEventListener("keydown", esc);
    });
  }

  function notify(message, opts) {
    opts = opts || {};
    var backdrop = _dialog(
      '<div class="modal" style="max-width:380px">' +
      '<div class="modal-header"><h3>' + escapeHtml(opts.title || "Уведомление") + '</h3></div>' +
      '<div class="modal-body">' + escapeHtml(message) + '</div>' +
      '<div class="modal-body" style="padding-top:0;display:flex;justify-content:flex-end">' +
      '<button type="button" class="btn primary" data-dlg-ok>OK</button>' +
      '</div></div>'
    );
    function done() { backdrop.remove(); }
    backdrop.querySelector("[data-dlg-ok]").addEventListener("click", done);
    backdrop.addEventListener("click", function (e) { if (e.target === backdrop) done(); });
    var esc = function (e) {
      if (e.key === "Escape") { document.removeEventListener("keydown", esc); done(); }
    };
    document.addEventListener("keydown", esc);
  }

  function confirmSubmit(form, message, opts) {
    confirmDialog(message, opts).then(function (ok) { if (ok) form.submit(); });
  }

  window.confirmSubmit = confirmSubmit;
  window.confirmDialog = confirmDialog;
  window.notify = notify;

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

  /* ---------- Мессенджер (чаты + сообщения) ---------- */
  var fab = document.getElementById("chat-fab");
  var popup = document.getElementById("chat-popup");
  var chatBackdrop = document.getElementById("chat-backdrop");
  var chatClose = document.getElementById("chat-close");
  var chatSend = document.getElementById("chat-send");
  var chatInput = document.getElementById("chat-input");
  var chatMessages = document.getElementById("chat-messages");
  var chatList = document.getElementById("chat-list");
  var chatSearch = document.getElementById("chat-search");
  var chatCurrentName = document.getElementById("chat-current-name");

  var allChats = [];
  var currentChatId = null;
  var lastMessageId = 0;
  var pollTimer = null;

  function toggleChat(open) {
    if (!popup) return;
    var shouldOpen = open !== undefined ? open : !popup.classList.contains("open");
    if (shouldOpen) {
      popup.classList.add("open");
      if (chatBackdrop) chatBackdrop.classList.add("open");
      loadChats();
      startPolling();
    } else {
      popup.classList.remove("open");
      if (chatBackdrop) chatBackdrop.classList.remove("open");
      stopPolling();
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function fmtTime(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    return d.getHours() + ":" + String(d.getMinutes()).padStart(2, "0");
  }

  function channelLabel(channel) {
    return { internal: "Клиент", telegram: "Telegram", maks: "Макс", site: "Сайт" }[channel] || channel;
  }

  function loadChats() {
    fetch("/api/chats")
      .catch(function () { return { json: function () { return []; } }; })
      .then(function (r) { return r.json(); })
      .then(function (chats) {
        allChats = chats || [];
        renderChatList();
      })
      .catch(function () {});
  }

  function renderChatList() {
    if (!chatList) return;
    var q = (chatSearch && chatSearch.value || "").toLowerCase().trim();
    chatList.innerHTML = "";
    allChats.forEach(function (c) {
      if (q && c.name.toLowerCase().indexOf(q) === -1) return;
      var el = document.createElement("div");
      el.className = "chat-item" + (c.id === currentChatId ? " active" : "");
      el.innerHTML =
        '<div class="chat-avatar"></div>' +
        '<div class="chat-info"><div class="chat-name"></div><div class="chat-last"></div></div>' +
        '<span class="chat-badge"></span>';
      el.querySelector(".chat-avatar").textContent = (c.name[0] || "?").toUpperCase();
      el.querySelector(".chat-name").textContent = c.name;
      el.querySelector(".chat-last").textContent = channelLabel(c.channel);
      el.querySelector(".chat-badge").textContent = channelLabel(c.channel);
      el.addEventListener("click", function () { openChat(c); });
      chatList.appendChild(el);
    });
  }

  function openChat(c) {
    currentChatId = c.id;
    if (chatCurrentName) chatCurrentName.textContent = c.name;
    renderChatList();
    fetch("/api/chats/" + c.id + "/messages")
      .then(function (r) { return r.json(); })
      .then(function (msgs) { renderMessages(msgs || []); pollUnread(); })
      .catch(function () {});
  }

  function appendMessage(m) {
    if (!chatMessages) return;
    var el = document.createElement("div");
    el.className = "msg " + (m.direction === "in" ? "incoming" : "outgoing");
    el.innerHTML = '<span></span><span class="time">' + fmtTime(m.created_at) + "</span>";
    el.querySelector("span").textContent = m.text;
    chatMessages.appendChild(el);
    if (m.id > lastMessageId) lastMessageId = m.id;
  }

  function renderMessages(msgs) {
    if (!chatMessages) return;
    chatMessages.innerHTML = "";
    lastMessageId = 0;
    if (!msgs.length) {
      chatMessages.innerHTML = '<div class="messenger-empty">Нет сообщений</div>';
      return;
    }
    msgs.forEach(appendMessage);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function refreshMessages() {
    if (!currentChatId) return;
    fetch("/api/chats/" + currentChatId + "/messages")
      .then(function (r) { return r.json(); })
      .then(function (msgs) {
        var hadNew = false;
        (msgs || []).forEach(function (m) {
          if (m.id > lastMessageId) { appendMessage(m); hadNew = true; }
        });
        if (hadNew) chatMessages.scrollTop = chatMessages.scrollHeight;
      })
      .catch(function () {});
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(function () {
      loadChats();
      refreshMessages();
    }, 3000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function send() {
    if (!chatInput || !chatInput.value.trim() || !currentChatId) return;
    var text = chatInput.value.trim();
    chatInput.value = "";
    fetch("/api/chats/" + currentChatId + "/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text }),
    })
      .then(function (r) { return r.json(); })
      .then(function () { refreshMessages(); })
      .catch(function () {});
  }

  if (fab) fab.addEventListener("click", function () { toggleChat(); });
  if (chatClose) chatClose.addEventListener("click", function () { toggleChat(false); });
  if (chatBackdrop) chatBackdrop.addEventListener("click", function () { toggleChat(false); });
  if (chatSend) chatSend.addEventListener("click", send);
  if (chatInput) {
    chatInput.addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
  }
  if (chatSearch) chatSearch.addEventListener("input", renderChatList);

  /* ---------- Непрочитанные сообщения: бейдж, пульс и тост ---------- */
  var chatBadge = document.getElementById("chat-badge");
  var chatToast = document.getElementById("chat-toast");
  var lastUnreadCount = 0;
  var toastTimer = null;

  function showChatToast(data) {
    if (!chatToast) return;
    var name = (data && data.last && data.last.name) || "";
    var text = (data && data.last && data.last.text) || "";
    chatToast.innerHTML =
      '<div class="t-title">Новое сообщение' + (name ? " · " + escapeHtml(name) : "") + "</div>" +
      (text ? '<div class="t-text">' + escapeHtml(text) + "</div>" : "");
    chatToast.hidden = false;
    requestAnimationFrame(function () { chatToast.classList.add("show"); });
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      chatToast.classList.remove("show");
      setTimeout(function () { chatToast.hidden = true; }, 300);
    }, 4000);
  }

  function updateChatBadge(unread) {
    if (chatBadge) {
      chatBadge.textContent = unread > 99 ? "99+" : String(unread);
      chatBadge.hidden = unread <= 0;
    }
    var fabEl = document.getElementById("chat-fab");
    if (fabEl) fabEl.classList.toggle("unread", unread > 0);
  }

  function pollUnread() {
    fetch("/api/chats/unread")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var unread = data.unread || 0;
        updateChatBadge(unread);
        var chatOpen = popup && popup.classList.contains("open");
        if (unread > lastUnreadCount && !chatOpen) showChatToast(data);
        lastUnreadCount = unread;
      })
      .catch(function () {});
  }

  if (fab) {
    pollUnread();
    setInterval(pollUnread, 8000);
  }
  if (chatToast) chatToast.addEventListener("click", function () { toggleChat(true); });

  /* ---------- Боковое меню: клик-переключатель (для тач-устройств) ---------- */
  document.querySelectorAll(".nav-group-header").forEach(function (header) {
    header.addEventListener("click", function () {
      header.parentElement.classList.toggle("open");
    });
  });

  /* ---------- Редактирование по клику на строке таблицы ---------- */
  document.querySelectorAll("tr[data-edit]").forEach(function (row) {
    row.addEventListener("click", function (e) {
      if (e.target.closest("a, button, form, input, select, textarea")) return;
      var modal = document.getElementById(row.getAttribute("data-edit"));
      if (!modal) return;
      // Все формы с data-action-pattern получают актуальный action (в т.ч. «Удалить»).
      modal.querySelectorAll('form[data-action-pattern]').forEach(function (f) {
        var pattern = f.getAttribute("data-action-pattern");
        if (pattern && row.dataset.id) {
          f.action = pattern.replace("{id}", row.dataset.id);
        }
      });
      var form = modal.querySelector("form");
      if (form) {
        Object.keys(row.dataset).forEach(function (key) {
          if (key === "edit" || key === "id") return;
          var field = form.querySelector('[name="' + key + '"]');
          if (!field) return;
          if (field.type === "radio") {
            var target = form.querySelector('[name="' + key + '"][value="' + row.dataset[key] + '"]');
            if (target) target.checked = true;
          } else {
            field.value = row.dataset[key];
          }
        });
        if (typeof syncPriceMode === "function") syncPriceMode(form);
      }
      openModal(row.getAttribute("data-edit"));
    });
  });

  /* Переключатель «свободная цена / по виду цен» */
  window.syncPriceMode = function (form) {
    var checked = form.querySelector('input[name="price_mode"]:checked');
    var mode = checked ? checked.value : "free";
    var free = form.querySelector(".pm-field-free");
    var type = form.querySelector(".pm-field-type");
    if (free) free.style.display = mode === "free" ? "" : "none";
    if (type) type.style.display = mode === "by_type" ? "" : "none";
  };

  document.addEventListener("change", function (e) {
    if (e.target && e.target.name === "price_mode") {
      syncPriceMode(e.target.closest("form"));
    }
  });

  /* ---------- Цены номенклатуры по видам ---------- */
  var tipyEl = document.getElementById("tipy-data");
  var explicitEl = document.getElementById("explicit-data");
  var TIPY = tipyEl ? JSON.parse(tipyEl.textContent) : [];
  var EXPLICIT = explicitEl ? JSON.parse(explicitEl.textContent) : {};

  function renderPriceRows(nomenId, purchasePrice) {
    var container = document.getElementById("prices-rows");
    if (!container) return;
    container.innerHTML = "";
    TIPY.forEach(function (tip) {
      var auto = purchasePrice ? purchasePrice * (1 + (tip.markup_percent || 0) / 100) : 0;
      var explicit = (EXPLICIT[nomenId] || {})[tip.id];

      var row = document.createElement("div");
      row.className = "flex flex-between";
      row.style.cssText = "padding:8px 0;border-bottom:1px solid var(--border);align-items:center";

      var label = document.createElement("div");
      label.style.cssText = "flex:1;min-width:0";
      var name = document.createElement("div");
      name.style.cssText = "font-size:13px";
      name.textContent = tip.name;
      var hint = document.createElement("div");
      hint.className = "muted small";
      hint.textContent = "наценка " + (tip.markup_percent != null ? tip.markup_percent + "%" : "—") + " · авто " + auto.toFixed(2);
      label.appendChild(name);
      label.appendChild(hint);

      var input = document.createElement("input");
      input.type = "number";
      input.step = "0.01";
      input.name = "override_" + tip.id;
      input.style.cssText = "width:130px;text-align:right";
      input.placeholder = auto.toFixed(2);
      input.value = explicit != null ? explicit : "";

      row.appendChild(label);
      row.appendChild(input);
      container.appendChild(row);
    });
  }

  document.querySelectorAll("[data-prices-open]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var row = btn.closest("tr[data-id]");
      var modal = document.getElementById("modal-prices");
      if (!row || !modal) return;
      var id = row.dataset.id;
      var form = modal.querySelector("form");
      form.action = "/catalog/nomenklatura/" + id + "/prices";
      form.querySelector('[name="purchase_price"]').value = row.dataset.purchase_price || "";
      form.querySelector('[name="retail_price"]').value = row.dataset.retail_price || "";
      renderPriceRows(id, parseFloat(row.dataset.purchase_price) || 0);
      openModal("modal-prices");
    });
  });

  /* ---------- РМК (рабочее место кассира) ---------- */
  var rmkData = document.getElementById("rmk-data");
  if (rmkData) {
    initRMK(rmkData);
  }

  function initRMK(el) {
    var items = [];
    try { items = JSON.parse(el.textContent); } catch (e) { items = []; }

    var grid = document.getElementById("rmk-grid");
    var search = document.getElementById("rmk-search");
    var cartBody = document.getElementById("rmk-cart-body");
    var cartEmpty = document.getElementById("rmk-cart-empty");
    var totalEl = document.getElementById("rmk-total");
    var sellBtn = document.getElementById("rmk-sell");
    var returnBtn = document.getElementById("rmk-return");
    var skladSelect = document.getElementById("rmk-sklad");
    var receivedInput = document.getElementById("rmk-received");
    var changeEl = document.getElementById("rmk-change");

    // Корзина: id -> {name, qty, price}
    var cart = {};
    var currentTotal = 0;

    // Продажа заявки через РМК: id заявки и предзагрузка её позиций.
    var zakazId = null;
    var zakazIdEl = document.getElementById("rmk-zakaz-id");
    if (zakazIdEl) {
      var zid = parseInt(zakazIdEl.textContent, 10);
      if (zid) zakazId = zid;
    }
    var preload = [];
    var preloadEl = document.getElementById("rmk-preload");
    if (preloadEl) {
      try { preload = JSON.parse(preloadEl.textContent) || []; } catch (e) { preload = []; }
    }

    function money(n) {
      return (Math.round((Number(n) + Number.EPSILON) * 100) / 100).toFixed(2);
    }

    window.recalcChange = function () {
      var received = parseFloat(receivedInput ? receivedInput.value : 0) || 0;
      var change = received - currentTotal;
      if (changeEl) {
        changeEl.textContent = (change < 0 ? "−" : "") + money(Math.abs(change)) + " ₽";
        changeEl.style.color = change < 0 ? "var(--bad)" : "";
      }
      return change;
    };

    function renderGrid(filter) {
      var q = (filter || "").toLowerCase().trim();
      grid.innerHTML = "";
      items.forEach(function (it) {
        if (q && it.name.toLowerCase().indexOf(q) === -1) return;
        var elItem = document.createElement("div");
        elItem.className = "rmk-item";
        elItem.innerHTML =
          (it.image ? '<img class="thumb" src="/uploads/' + it.image + '" alt="">' : "") +
          '<div class="name"></div>' +
          (it.price ? '<div class="price">' + money(it.price) + " ₽</div>" : "");
        elItem.querySelector(".name").textContent = it.name;
        elItem.addEventListener("dblclick", function () {
          addToCart(it.id, it.name, it.price || 0, 1);
        });
        elItem.addEventListener("click", function () {
          addToCart(it.id, it.name, it.price || 0, 1);
        });
        grid.appendChild(elItem);
      });
    }

    function addToCart(id, name, price, qty) {
      if (cart[id]) {
        cart[id].qty += qty;
      } else {
        cart[id] = { name: name, price: price, qty: qty };
      }
      renderCart();
    }

    function recalc() {
      var total = 0;
      Object.keys(cart).forEach(function (id) {
        total += cart[id].qty * cart[id].price;
      });
      currentTotal = total;
      totalEl.textContent = money(total) + " ₽";
      recalcChange();
      return total;
    }

    function renderCart() {
      var ids = Object.keys(cart);
      cartEmpty.style.display = ids.length ? "none" : "";
      cartBody.innerHTML = "";
      ids.forEach(function (id) {
        var row = document.createElement("div");
        row.className = "cart-row";
        row.innerHTML =
          '<div class="c-name"></div>' +
          '<input class="c-qty" type="number" min="0.001" step="0.001">' +
          '<input class="c-price" type="number" min="0" step="0.01">' +
          '<div class="c-amount"></div>' +
          '<button class="c-del" title="Удалить">✕</button>';
        row.querySelector(".c-name").textContent = cart[id].name;
        var qtyInput = row.querySelector(".c-qty");
        var priceInput = row.querySelector(".c-price");
        var amountEl = row.querySelector(".c-amount");
        qtyInput.value = cart[id].qty;
        priceInput.value = cart[id].price;

        function updateAmount() {
          cart[id].qty = parseFloat(qtyInput.value) || 0;
          cart[id].price = parseFloat(priceInput.value) || 0;
          amountEl.textContent = money(cart[id].qty * cart[id].price);
          recalc();
        }
        qtyInput.addEventListener("input", updateAmount);
        priceInput.addEventListener("input", updateAmount);
        updateAmount();

        row.querySelector(".c-del").addEventListener("click", function () {
          delete cart[id];
          renderCart();
        });

        cartBody.appendChild(row);
      });
      recalc();
    }

    if (search) search.addEventListener("input", function () { renderGrid(search.value); });
    renderGrid();
    preload.forEach(function (it) { addToCart(it.id, it.name, it.price || 0, it.qty || 1); });
    renderCart();

    function doSell(isReturn) {
      var ids = Object.keys(cart);
      if (!ids.length) return;
      var lines = ids.map(function (id) {
        return {
          nomenklatura_id: parseInt(id, 10),
          quantity: cart[id].qty,
          price: cart[id].price,
        };
      });
      var skladId = skladSelect ? skladSelect.value : "";
      var received = parseFloat(receivedInput ? receivedInput.value : 0) || 0;
      if (!isReturn && received < currentTotal) {
        notify("Сумма оплаты меньше итога на " + money(currentTotal - received) + " ₽");
        return;
      }
      if (sellBtn) sellBtn.disabled = true;
      if (returnBtn) returnBtn.disabled = true;
      fetch("/rmk/sell", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sklad_id: skladId ? parseInt(skladId, 10) : null, items: lines, return: !!isReturn, received: received, zakaz_id: zakazId }),
      })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Ошибка"); });
          return r.json();
        })
        .then(function (data) {
          window.location.href = "/documents/" + data.id + "/print";
        })
        .catch(function (err) {
          notify("Ошибка: " + err.message, { title: "Ошибка" });
          if (sellBtn) sellBtn.disabled = false;
          if (returnBtn) returnBtn.disabled = false;
        });
    }

    if (sellBtn) sellBtn.addEventListener("click", function () { doSell(false); });
    if (returnBtn) returnBtn.addEventListener("click", function () { doSell(true); });
  }
})();
