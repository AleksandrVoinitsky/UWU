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

  /* ---------- Мессенджер (чаты + сообщения) ---------- */
  var fab = document.getElementById("chat-fab");
  var popup = document.getElementById("chat-popup");
  var chatClose = document.getElementById("chat-close");
  var chatSend = document.getElementById("chat-send");
  var chatInput = document.getElementById("chat-input");
  var chatMessages = document.getElementById("chat-messages");
  var chatList = document.getElementById("chat-list");
  var chatSearch = document.getElementById("chat-search");
  var chatCurrentName = document.getElementById("chat-current-name");

  var allChats = [];
  var currentChatId = null;

  function toggleChat(open) {
    if (!popup) return;
    var shouldOpen = open !== undefined ? open : !popup.classList.contains("open");
    if (shouldOpen) {
      popup.classList.add("open");
      loadChats();
    } else {
      popup.classList.remove("open");
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
    return { internal: "Клиент", telegram: "Telegram", maks: "Макс" }[channel] || channel;
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
      .then(function (msgs) { renderMessages(msgs || []); })
      .catch(function () {});
  }

  function renderMessages(msgs) {
    if (!chatMessages) return;
    chatMessages.innerHTML = "";
    if (!msgs.length) {
      chatMessages.innerHTML = '<div class="messenger-empty">Нет сообщений</div>';
      return;
    }
    msgs.forEach(function (m) {
      var el = document.createElement("div");
      el.className = "msg " + (m.direction === "in" ? "incoming" : "outgoing");
      el.innerHTML = '<span></span><span class="time">' + fmtTime(m.created_at) + "</span>";
      el.querySelector("span").textContent = m.text;
      chatMessages.appendChild(el);
    });
    chatMessages.scrollTop = chatMessages.scrollHeight;
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
      .then(function (m) {
        var el = document.createElement("div");
        el.className = "msg outgoing";
        el.innerHTML = '<span></span><span class="time">' + fmtTime(m.created_at) + "</span>";
        el.querySelector("span").textContent = m.text;
        chatMessages.appendChild(el);
        chatMessages.scrollTop = chatMessages.scrollHeight;
      })
      .catch(function () {});
  }

  if (fab) fab.addEventListener("click", function () { toggleChat(); });
  if (chatClose) chatClose.addEventListener("click", function () { toggleChat(false); });
  if (chatSend) chatSend.addEventListener("click", send);
  if (chatInput) {
    chatInput.addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
  }
  if (chatSearch) chatSearch.addEventListener("input", renderChatList);

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
      var form = modal.querySelector("form");
      if (form) {
        var pattern = form.getAttribute("data-action-pattern");
        if (pattern && row.dataset.id) {
          form.action = pattern.replace("{id}", row.dataset.id);
        }
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
        alert("Сумма оплаты меньше итога на " + money(currentTotal - received) + " ₽");
        return;
      }
      if (sellBtn) sellBtn.disabled = true;
      if (returnBtn) returnBtn.disabled = true;
      fetch("/rmk/sell", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sklad_id: skladId ? parseInt(skladId, 10) : null, items: lines, return: !!isReturn, received: received }),
      })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Ошибка"); });
          return r.json();
        })
        .then(function (data) {
          window.location.href = "/documents/" + data.id + "/print";
        })
        .catch(function (err) {
          alert("Ошибка: " + err.message);
          if (sellBtn) sellBtn.disabled = false;
          if (returnBtn) returnBtn.disabled = false;
        });
    }

    if (sellBtn) sellBtn.addEventListener("click", function () { doSell(false); });
    if (returnBtn) returnBtn.addEventListener("click", function () { doSell(true); });
  }
})();
