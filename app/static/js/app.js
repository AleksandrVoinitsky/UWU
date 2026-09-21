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
          if (field) field.value = row.dataset[key];
        });
      }
      openModal(row.getAttribute("data-edit"));
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
    var skladSelect = document.getElementById("rmk-sklad");

    // Корзина: id -> {name, qty, price}
    var cart = {};

    function money(n) {
      return (Math.round((Number(n) + Number.EPSILON) * 100) / 100).toFixed(2);
    }

    function renderGrid(filter) {
      var q = (filter || "").toLowerCase().trim();
      grid.innerHTML = "";
      items.forEach(function (it) {
        if (q && it.name.toLowerCase().indexOf(q) === -1) return;
        var elItem = document.createElement("div");
        elItem.className = "rmk-item";
        elItem.innerHTML =
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
      totalEl.textContent = money(total) + " ₽";
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

    if (sellBtn) {
      sellBtn.addEventListener("click", function () {
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
        sellBtn.disabled = true;
        fetch("/rmk/sell", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sklad_id: skladId ? parseInt(skladId, 10) : null, items: lines }),
        })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "Ошибка"); });
            return r.json();
          })
          .then(function (data) {
            window.location.href = "/documents/" + data.id + "/print";
          })
          .catch(function (err) {
            alert("Не удалось провести продажу: " + err.message);
            sellBtn.disabled = false;
          });
      });
    }
  }
})();
