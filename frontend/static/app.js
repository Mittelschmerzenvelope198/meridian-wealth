// Data Explorer — tabbed panel switching driven by the ?view= query param.
(function () {
    const container = document.querySelector("[data-tabs]");
    if (!container) return; // not on the data page

    const tabs = Array.from(container.querySelectorAll(".tab"));
    const panels = Array.from(container.querySelectorAll(".panel"));
    const valid = tabs.map(function (t) { return t.dataset.tab; });

    function activate(name) {
        if (valid.indexOf(name) === -1) name = valid[0];
        tabs.forEach(function (t) { t.classList.toggle("active", t.dataset.tab === name); });
        panels.forEach(function (p) { p.classList.toggle("active", p.id === "panel-" + name); });
    }

    tabs.forEach(function (t) {
        t.addEventListener("click", function () {
            activate(t.dataset.tab);
            history.replaceState(null, "", "?view=" + t.dataset.tab);
        });
    });

    // Initial selection from ?view= (set by the landing-page cards), else first tab.
    const params = new URLSearchParams(window.location.search);
    activate(params.get("view") || valid[0]);
})();

// Streaming chat workspace: WebSocket -> markdown answer + tool trace + verbose log.
(function () {
    const form = document.getElementById("chat-form");
    const input = document.getElementById("query");
    const messages = document.getElementById("messages");
    const sendBtn = document.getElementById("send-btn");
    const trace = document.getElementById("trace");
    const execLog = document.getElementById("exec-log");

    if (!form) return; // not on the chat page

    if (window.marked) {
        marked.setOptions({ gfm: true, breaks: true });
    }

    function renderMarkdown(text) {
        if (window.marked && window.DOMPurify) {
            return DOMPurify.sanitize(marked.parse(text || ""));
        }
        // Fallback: escape and preserve newlines.
        const div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML.replace(/\n/g, "<br>");
    }

    // Renders markdown into `el` and then highlights key financial metrics so they
    // stand out (₹ amounts, percentages, client IDs) regardless of the model's markup.
    function setMarkdown(el, text) {
        el.innerHTML = renderMarkdown(text);
        highlightMetrics(el);
    }

    // ₹ amounts (with optional lakh/crore unit), percentages, and CLT-xxx IDs.
    const METRIC_RE = /(₹\s?[\d,]+(?:\.\d+)?(?:\s?(?:lakh|crore|cr))?)|(\d+(?:\.\d+)?\s?%)|(\bCLT-\d{2,}\b)/gi;

    function highlightMetrics(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode: function (node) {
                if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
                // Skip code, links, and existing highlight spans.
                const tag = node.parentNode && node.parentNode.nodeName;
                if (tag === "CODE" || tag === "PRE" || tag === "A") return NodeFilter.FILTER_REJECT;
                if (node.parentNode && node.parentNode.classList &&
                    (node.parentNode.classList.contains("metric") || node.parentNode.classList.contains("chip-id"))) {
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            }
        });

        const targets = [];
        let n;
        while ((n = walker.nextNode())) {
            METRIC_RE.lastIndex = 0;
            if (METRIC_RE.test(n.nodeValue)) targets.push(n);
        }

        targets.forEach(function (node) {
            const text = node.nodeValue;
            const frag = document.createDocumentFragment();
            let last = 0, m;
            METRIC_RE.lastIndex = 0;
            while ((m = METRIC_RE.exec(text)) !== null) {
                if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
                const span = document.createElement("span");
                if (m[1]) { span.className = "metric metric-money"; }
                else if (m[2]) { span.className = "metric metric-pct"; }
                else { span.className = "chip-id"; }
                span.textContent = m[0];
                frag.appendChild(span);
                last = m.index + m[0].length;
            }
            if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
            node.parentNode.replaceChild(frag, node);
        });
    }

    function scrollToBottom() { messages.scrollTop = messages.scrollHeight; }

    function addUserMessage(text) {
        const wrap = document.createElement("div");
        wrap.className = "msg msg-user";
        const role = document.createElement("div");
        role.className = "msg-role";
        role.textContent = "You";
        const body = document.createElement("div");
        body.className = "msg-body";
        body.textContent = text;
        wrap.appendChild(role);
        wrap.appendChild(body);
        messages.appendChild(wrap);
        scrollToBottom();
    }

    // Creates an agent message bubble that we progressively fill as tokens arrive.
    function createAgentMessage() {
        const wrap = document.createElement("div");
        wrap.className = "msg msg-agent";
        wrap.innerHTML =
            '<div class="msg-role">Agent</div>' +
            '<div class="msg-body markdown"><div class="typing"><span></span><span></span><span></span></div></div>';
        messages.appendChild(wrap);
        scrollToBottom();
        return wrap.querySelector(".msg-body");
    }

    // ---- Tool trace (concise) ----------------------------------------------
    function resetTrace() {
        trace.innerHTML = '<p class="trace-empty">Waiting for tool activity…</p>';
    }

    function argsToHtml(args) {
        if (!args || typeof args !== "object" || !Object.keys(args).length) return "";
        let rows = "";
        Object.keys(args).forEach(function (k) {
            let v = args[k];
            if (typeof v === "object") v = JSON.stringify(v);
            rows += '<div class="t-arg"><span class="t-key">' + escapeHtml(k) + '</span>' +
                    '<span class="t-val">' + escapeHtml(String(v)) + '</span></div>';
        });
        return '<div class="t-args">' + rows + "</div>";
    }

    function addToolCall(ev) {
        const empty = trace.querySelector(".trace-empty");
        if (empty) empty.remove();
        const card = document.createElement("div");
        card.className = "t-card running";
        card.dataset.tid = ev.id || ("anon-" + Math.random().toString(36).slice(2));
        card.innerHTML =
            '<div class="t-head"><span class="t-badge">' + escapeHtml(ev.name || "tool") + '</span>' +
            '<span class="t-status">running…</span></div>' +
            argsToHtml(ev.args);
        trace.appendChild(card);
    }

    function addToolResult(ev) {
        let card = ev.id ? trace.querySelector('.t-card[data-tid="' + cssEscape(ev.id) + '"]') : null;
        if (!card) {
            // Result without a matching call card — create a standalone one.
            addToolCall({ id: ev.id, name: ev.name, args: {} });
            card = trace.querySelector('.t-card[data-tid="' + cssEscape(ev.id) + '"]');
        }
        if (!card) return;
        card.classList.remove("running");
        card.classList.add("done");
        const status = card.querySelector(".t-status");
        if (status) status.textContent = "done";
        const res = document.createElement("div");
        res.className = "t-result";
        res.innerHTML = '<span class="t-result-label">result</span><span class="t-result-val">' +
                        escapeHtml(ev.preview || "") + "</span>";
        card.appendChild(res);
    }

    // ---- Verbose execution trace -------------------------------------------
    function addLog(ev) {
        const line = document.createElement("div");
        line.className = "log-line log-" + (ev.level || "info");
        const tag = document.createElement("span");
        tag.className = "log-tag";
        tag.textContent = (ev.level || "info").toUpperCase();
        const body = document.createElement("span");
        body.className = "log-body";
        body.textContent = ev.text || "";
        line.appendChild(tag);
        line.appendChild(body);
        execLog.appendChild(line);
        execLog.scrollTop = execLog.scrollHeight;
    }

    // ---- Helpers ------------------------------------------------------------
    function escapeHtml(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }
    function cssEscape(s) {
        return String(s).replace(/["\\]/g, "\\$&");
    }

    // ---- Run a query over the WebSocket ------------------------------------
    function sendQuery(query) {
        sendBtn.disabled = true;
        resetTrace();
        execLog.innerHTML = "";

        const bodyEl = createAgentMessage();
        let answer = "";
        let firstToken = true;
        let renderPending = false;

        // Throttle re-render+highlight to one paint per frame while tokens stream in.
        function scheduleRender() {
            if (renderPending) return;
            renderPending = true;
            requestAnimationFrame(function () {
                renderPending = false;
                setMarkdown(bodyEl, answer);
                scrollToBottom();
            });
        }

        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(proto + "//" + window.location.host + "/ws/chat");

        ws.onopen = function () { ws.send(JSON.stringify({ query: query })); };

        ws.onmessage = function (e) {
            let ev;
            try { ev = JSON.parse(e.data); } catch (err) { return; }

            switch (ev.type) {
                case "token":
                    if (firstToken) { bodyEl.innerHTML = ""; firstToken = false; }
                    answer += ev.text;
                    scheduleRender();
                    break;
                case "tool":
                    addToolCall(ev);
                    break;
                case "tool_result":
                    addToolResult(ev);
                    break;
                case "log":
                    addLog(ev);
                    break;
                case "error":
                    if (firstToken) { bodyEl.innerHTML = ""; firstToken = false; }
                    setMarkdown(bodyEl, (answer ? answer + "\n\n" : "") + "⚠️ **Error:** " + ev.detail);
                    break;
                case "done":
                    if (firstToken) {
                        bodyEl.textContent = "No response generated.";
                    } else {
                        setMarkdown(bodyEl, answer); // final, un-throttled render
                        scrollToBottom();
                    }
                    break;
            }
        };

        ws.onerror = function () {
            if (firstToken) { bodyEl.textContent = "⚠️ WebSocket connection error."; }
            sendBtn.disabled = false;
        };
        ws.onclose = function () { sendBtn.disabled = false; };
    }

    form.addEventListener("submit", function (e) {
        e.preventDefault();
        const query = input.value.trim();
        if (!query) return;
        addUserMessage(query);
        input.value = "";
        sendQuery(query);
    });

    // Submit on Enter, newline on Shift+Enter.
    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            form.requestSubmit();
        }
    });
})();
