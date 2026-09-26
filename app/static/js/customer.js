/* UWU Shop — клиентский сайт/MiniApp: корзина (клик по карточке, анимация, степпер). */

async function addToCart(cardEl, nomenklaturaId) {
  try {
    var resp = await fetch('/shop/api/cart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nomenklatura_id: nomenklaturaId, quantity: 1 })
    });
    if (resp.status === 401) { window.location = '/shop/login'; return; }
    if (!resp.ok) return;
    var data = await resp.json();
    setCartBadge((data.items || []).reduce(function (s, i) { return s + Number(i.quantity); }, 0));
    animateFly(cardEl);
  } catch (e) { /* noop */ }
}

async function setCartQty(itemId, qty) {
  try {
    var resp = await fetch('/shop/api/cart/' + itemId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quantity: qty })
    });
    if (resp.status === 401) { window.location = '/shop/login'; return; }
    if (!resp.ok) return;
    var data = await resp.json();
    setCartBadge((data.items || []).reduce(function (s, i) { return s + Number(i.quantity); }, 0));
    updateCartTotals(data);
  } catch (e) { /* noop */ }
}

function setCartBadge(count) {
  var badge = document.getElementById('cart-badge');
  if (!badge) return;
  badge.textContent = count;
  badge.hidden = count <= 0;
}

function updateCartTotals(data) {
  // Обновляем суммы строк по ответу сервера.
  var items = data.items || [];
  var byId = {};
  items.forEach(function (i) { byId[i.id] = i; });
  document.querySelectorAll('[data-cart-row]').forEach(function (row) {
    var id = row.getAttribute('data-cart-row');
    var item = byId[id];
    if (!item) return;
    var amt = row.querySelector('.cart-amount');
    if (amt) amt.textContent = Number(item.amount).toFixed(2) + ' ₽';
  });
  var total = document.getElementById('cart-total');
  if (total) total.textContent = Number(data.total).toFixed(2) + ' ₽';
}

function animateFly(cardEl) {
  var cart = document.getElementById('cart-anchor');
  if (!cart) return;
  var imgEl = cardEl.querySelector('.product-img img');
  var box = cardEl.querySelector('.product-img') || cardEl;
  var from = box.getBoundingClientRect();
  var to = cart.getBoundingClientRect();

  var clone = document.createElement('div');
  clone.className = 'fly-clone';
  clone.style.left = from.left + 'px';
  clone.style.top = from.top + 'px';
  clone.style.width = from.width + 'px';
  clone.style.height = from.height + 'px';
  if (imgEl) {
    clone.innerHTML = '<img src="' + imgEl.src + '" alt="">';
  } else {
    clone.style.background = '#e3e3e8';
  }
  document.body.appendChild(clone);

  var dx = (to.left + to.width / 2) - (from.left + from.width / 2);
  var dy = (to.top + to.height / 2) - (from.top + from.height / 2);
  var anim = clone.animate([
    { transform: 'translate(0,0) scale(1)', opacity: 1 },
    { transform: 'translate(' + dx + 'px,' + dy + 'px) scale(0.08)', opacity: 0.25 }
  ], { duration: 650, easing: 'cubic-bezier(0.22,1,0.36,1)' });
  anim.onfinish = function () { clone.remove(); };
}

/* Степпер корзины: +/- и ручной ввод. */
function stepQty(itemId, delta) {
  var input = document.querySelector('[data-qty-input="' + itemId + '"]');
  if (!input) return;
  var v = (parseFloat(input.value) || 0) + delta;
  if (v < 0) v = 0;
  input.value = v;
  if (v === 0) { setCartQty(itemId, 0); window.location.reload(); return; }
  setCartQty(itemId, v);
}

document.addEventListener('DOMContentLoaded', function () {
  // Инициализация бейджа корзины (если авторизованы).
  fetch('/shop/api/cart')
    .then(function (r) { if (r.ok) return r.json(); })
    .then(function (data) {
      if (!data || !data.items) return;
      setCartBadge(data.items.reduce(function (s, i) { return s + Number(i.quantity); }, 0));
    })
    .catch(function () {});

  // Ручной ввод количества в корзине (по Enter/потере фокуса).
  document.querySelectorAll('[data-qty-input]').forEach(function (input) {
    input.addEventListener('change', function () {
      var itemId = input.getAttribute('data-qty-input');
      var v = parseFloat(input.value) || 0;
      if (v < 0) v = 0;
      input.value = v;
      if (v === 0) { setCartQty(itemId, 0); window.location.reload(); return; }
      setCartQty(itemId, v);
    });
  });
});

/* ---------- Чат с продавцом ---------- */
(function () {
  var fab = document.getElementById('shop-chat-fab');
  if (!fab) return;

  var popup = document.getElementById('shop-chat-popup');
  var backdrop = document.getElementById('shop-chat-backdrop');
  var closeBtn = document.getElementById('shop-chat-close');
  var messagesEl = document.getElementById('shop-chat-messages');
  var input = document.getElementById('shop-chat-text');
  var sendBtn = document.getElementById('shop-chat-send');

  var opened = false;
  var pollTimer = null;
  var lastId = 0;

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function fmtTime(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    return d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0');
  }

  function toggle(open) {
    opened = open !== undefined ? open : !opened;
    popup.classList.toggle('open', opened);
    backdrop.classList.toggle('open', opened);
    if (opened) { load(); startPolling(); } else { stopPolling(); }
  }

  function appendMsg(m) {
    var el = document.createElement('div');
    // Для покупателя его сообщения — справа, ответы продавца — слева.
    el.className = 'msg ' + (m.direction === 'in' ? 'outgoing' : 'incoming');
    el.innerHTML = '<span></span><span class="time">' + fmtTime(m.created_at) + '</span>';
    el.querySelector('span').textContent = m.text;
    messagesEl.appendChild(el);
    if (m.id > lastId) lastId = m.id;
  }

  function render(messages) {
    messagesEl.innerHTML = '';
    lastId = 0;
    if (!messages || !messages.length) {
      messagesEl.innerHTML = '<div class="shop-chat-empty">Напишите нам — мы на связи</div>';
      return;
    }
    messages.forEach(appendMsg);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function load() {
    fetch('/shop/api/chat')
      .then(function (r) { if (!r.ok) throw new Error('load failed'); return r.json(); })
      .then(function (data) { render(data.messages); })
      .catch(function () {});
  }

  function refresh() {
    fetch('/shop/api/chat')
      .then(function (r) { if (!r.ok) throw new Error('load failed'); return r.json(); })
      .then(function (data) {
        var hadNew = false;
        (data.messages || []).forEach(function (m) {
          if (m.id > lastId) { appendMsg(m); hadNew = true; }
        });
        if (hadNew) messagesEl.scrollTop = messagesEl.scrollHeight;
      })
      .catch(function () {});
  }

  function send() {
    var text = (input.value || '').trim();
    if (!text) return;
    input.value = '';
    fetch('/shop/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text })
    })
      .then(function (r) { if (!r.ok) throw new Error('send failed'); return r.json(); })
      .then(function () { refresh(); })
      .catch(function () { input.value = text; });
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(refresh, 4000);
  }
  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  fab.addEventListener('click', function () { toggle(); });
  if (closeBtn) closeBtn.addEventListener('click', function () { toggle(false); });
  if (backdrop) backdrop.addEventListener('click', function () { toggle(false); });
  if (sendBtn) sendBtn.addEventListener('click', send);
  if (input) input.addEventListener('keydown', function (e) { if (e.key === 'Enter') send(); });
})();
