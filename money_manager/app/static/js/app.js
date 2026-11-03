(function () {
  const BASE = window.INGRESS_PATH || "";
  const api = (path) => `${BASE}${path}`;

  let categories = [];
  let accounts = [];
  let txOffset = 0;
  const txLimit = 50;
  let monthlyChart = null;
  let categoryChart = null;
  let ruleSource = null;

  // ---------------------------------------------------------------- tabs --
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "dashboard") loadDashboard();
      if (btn.dataset.tab === "transactions") loadTransactions();
      if (btn.dataset.tab === "accounts") loadAccounts();
      if (btn.dataset.tab === "categories") loadCategoriesAndRules();
    });
  });

  function fmtMoney(value) {
    const n = Number(value || 0);
    return n.toLocaleString(undefined, { style: "currency", currency: "EUR" });
  }

  async function loadAccounts() {
    accounts = await fetch(api("/api/accounts")).then((r) => r.json());
    ["dash-account", "tx-account", "export-account"].forEach((id) => {
      const select = document.getElementById(id);
      const current = select.value;
      select.replaceChildren(new Option("All accounts", ""));
      accounts.forEach(({ account, name, count }) => {
        const label = account ? `${name ? `${name} (${account})` : account} (${count})` : `Unassigned (${count})`;
        select.add(new Option(label, account || "__unassigned__"));
      });
      select.value = [...select.options].some((option) => option.value === current) ? current : "";
    });
    const list = document.getElementById("known-accounts");
    list.replaceChildren();
    accounts.filter((item) => item.account).forEach(({ account, name }) => {
      const option = document.createElement("option");
      option.value = account;
      option.label = name ? `${name} (${account})` : account;
      list.appendChild(option);
    });
    renderAccounts();
  }

  function renderAccounts() {
    const tbody = document.querySelector("#accounts-table tbody");
    tbody.replaceChildren();
    const message = document.getElementById("accounts-message");
    if (!accounts.length) message.textContent = "No accounts yet. Import a statement to get started.";
    else message.textContent = "";
    accounts.forEach(({ account, name, count }) => {
      const tr = document.createElement("tr");
      const identifier = tr.insertCell();
      identifier.textContent = account || "Unassigned";
      const nameCell = tr.insertCell();
      const countCell = tr.insertCell();
      countCell.textContent = count;
      const actionCell = tr.insertCell();
      if (account) {
        const input = document.createElement("input");
        input.type = "text";
        input.maxLength = 80;
        input.value = name;
        input.placeholder = "e.g. Everyday account";
        input.setAttribute("aria-label", `Display name for ${account}`);
        nameCell.appendChild(input);
        const save = document.createElement("button");
        save.textContent = "Save";
        actionCell.appendChild(save);
        const saveName = async () => {
          save.disabled = true;
          try {
            const response = await fetch(api(`/api/accounts/${encodeURIComponent(account)}`), {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: input.value }),
            });
            if (!response.ok) throw new Error((await response.json()).error || "Could not save name");
            await loadAccounts();
            message.textContent = `Saved name for ${account}.`;
            if (document.getElementById("tab-transactions").classList.contains("active")) loadTransactions();
          } catch (error) {
            message.textContent = error.message;
            save.disabled = false;
          }
        };
        save.addEventListener("click", saveName);
        input.addEventListener("keydown", (event) => {
          if (event.key === "Enter") saveName();
        });
      } else {
        nameCell.textContent = "Assign these transactions on the Transactions page";
      }
      tbody.appendChild(tr);
    });
  }

  // ----------------------------------------------------------- dashboard --
  async function loadDashboard() {
    const from = document.getElementById("dash-from").value;
    const to = document.getElementById("dash-to").value;
    const qs = new URLSearchParams();
    const account = document.getElementById("dash-account").value;
    if (account) qs.set("account", account);
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);

    const [totals, monthly, byCategory] = await Promise.all([
      fetch(api(`/api/summary/totals?${qs}`)).then((r) => r.json()),
      fetch(api(`/api/summary/monthly?${qs}`)).then((r) => r.json()),
      fetch(api(`/api/summary/categories?${qs}`)).then((r) => r.json()),
    ]);

    document.getElementById("stat-income").textContent = fmtMoney(totals.income);
    document.getElementById("stat-expense").textContent = fmtMoney(totals.expense);
    document.getElementById("stat-net").textContent = fmtMoney(totals.net);
    document.getElementById("stat-uncat").textContent = totals.uncategorized;

    const months = monthly.map((m) => m.month);
    const income = monthly.map((m) => m.income);
    const expense = monthly.map((m) => m.expense);

    const monthlyCtx = document.getElementById("chart-monthly").getContext("2d");
    if (monthlyChart) monthlyChart.destroy();
    monthlyChart = new Chart(monthlyCtx, {
      type: "bar",
      data: {
        labels: months,
        datasets: [
          { label: "Income", data: income, backgroundColor: "#2ecc71" },
          { label: "Expenses", data: expense, backgroundColor: "#e74c3c" },
        ],
      },
      options: {
        responsive: true,
        scales: { y: { beginAtZero: true } },
      },
    });

    const catCtx = document.getElementById("chart-categories").getContext("2d");
    if (categoryChart) categoryChart.destroy();
    categoryChart = new Chart(catCtx, {
      type: "doughnut",
      data: {
        labels: byCategory.map((c) => c.category),
        datasets: [
          {
            data: byCategory.map((c) => c.total),
            backgroundColor: byCategory.map((c) => c.color),
          },
        ],
      },
      options: { responsive: true },
    });
  }

  document.getElementById("dash-refresh").addEventListener("click", loadDashboard);
  document.getElementById("dash-account").addEventListener("change", loadDashboard);

  // -------------------------------------------------------- transactions --
  async function loadCategoryOptionsForFilter() {
    const select = document.getElementById("tx-category-filter");
    select.innerHTML = '<option value="">All categories</option>';
    categories.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      select.appendChild(opt);
    });
  }

  async function loadTransactions() {
    const search = document.getElementById("tx-search").value;
    const categoryId = document.getElementById("tx-category-filter").value;
    const account = document.getElementById("tx-account").value;
    const uncategorized = document.getElementById("tx-uncategorized-only").checked;

    const qs = new URLSearchParams();
    if (search) qs.set("search", search);
    if (categoryId) qs.set("category_id", categoryId);
    if (account) qs.set("account", account);
    if (uncategorized) qs.set("uncategorized", "1");
    qs.set("limit", txLimit);
    qs.set("offset", txOffset);

    const data = await fetch(api(`/api/transactions?${qs}`)).then((r) => r.json());
    const tbody = document.getElementById("tx-rows");
    tbody.innerHTML = "";

    data.items.forEach((tx) => {
      const tr = document.createElement("tr");
      const amountClass = tx.amount >= 0 ? "amount-pos" : "amount-neg";
      const catSelect = document.createElement("select");
      const noneOpt = document.createElement("option");
      noneOpt.value = "";
      noneOpt.textContent = "(none)";
      catSelect.appendChild(noneOpt);
      categories.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = c.name;
        if (tx.category_id === c.id) opt.selected = true;
        catSelect.appendChild(opt);
      });
      catSelect.addEventListener("change", async () => {
        await fetch(api(`/api/transactions/${tx.id}`), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category_id: catSelect.value ? Number(catSelect.value) : null }),
        });
      });

      const addCell = (text) => {
        const cell = tr.insertCell();
        cell.textContent = text;
        return cell;
      };
      addCell(tx.date);
      const accountCell = addCell("");
      const accountButton = document.createElement("button");
      const accountName = accounts.find((item) => item.account === tx.account)?.name;
      accountButton.textContent = accountName || tx.account || "Unassigned";
      accountButton.title = `Click to change account${tx.account ? ` (${tx.account})` : ""}`;
      accountButton.addEventListener("click", async () => {
        const value = prompt("Account identifier (empty for unassigned):", tx.account || "");
        if (value === null) return;
        const response = await fetch(api(`/api/transactions/${tx.id}`), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ account: value }),
        });
        if (!response.ok) {
          alert("Could not change account.");
          return;
        }
        await loadAccounts();
        loadTransactions();
        loadDashboard();
      });
      accountCell.appendChild(accountButton);
      addCell(tx.description || "");
      addCell(tx.counterparty || "");
      addCell(fmtMoney(tx.amount)).className = amountClass;
      addCell("").appendChild(catSelect);
      const actions = addCell("");
      actions.className = "row-actions";
      const ruleButton = document.createElement("button");
      ruleButton.textContent = "Create rule";
      ruleButton.addEventListener("click", () => openRuleDialog(tx));
      actions.appendChild(ruleButton);
      const deleteButton = document.createElement("button");
      deleteButton.className = "danger";
      deleteButton.textContent = "Delete";
      actions.appendChild(deleteButton);
      deleteButton.addEventListener("click", async () => {
        if (!confirm("Delete this transaction?")) return;
        await fetch(api(`/api/transactions/${tx.id}`), { method: "DELETE" });
        await loadAccounts();
        loadTransactions();
      });
      tbody.appendChild(tr);
    });

    document.getElementById("tx-page-info").textContent =
      `${data.total === 0 ? 0 : txOffset + 1}-${Math.min(txOffset + txLimit, data.total)} of ${data.total}`;
  }

  function openRuleDialog(tx) {
    ruleSource = tx;
    const form = document.getElementById("rule-dialog-form");
    form.reset();
    document.getElementById("rule-dialog-error").textContent = "";
    document.getElementById("rule-dialog-source").textContent =
      `${tx.date} · ${fmtMoney(tx.amount)} · ${tx.counterparty || tx.description || tx.iban || "Transaction"}`;

    const field = document.getElementById("rule-dialog-field");
    field.value = tx.counterparty?.trim() ? "counterparty" : tx.description?.trim() ? "description" : "iban";
    document.getElementById("rule-dialog-pattern").value = (tx[field.value] || "").trim();
    const category = document.getElementById("rule-dialog-category");
    category.replaceChildren(new Option("Choose a category", ""));
    categories.forEach((item) => category.add(new Option(item.name, item.id)));
    category.value = tx.category_id ? String(tx.category_id) : "";
    document.getElementById("rule-dialog").showModal();
  }

  document.getElementById("rule-dialog-field").addEventListener("change", (event) => {
    const field = event.target.value;
    if (field !== "any") {
      document.getElementById("rule-dialog-pattern").value = (ruleSource?.[field] || "").trim();
    }
  });
  document.getElementById("rule-dialog-cancel").addEventListener("click", () => {
    document.getElementById("rule-dialog").close();
  });
  document.getElementById("rule-dialog-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!ruleSource) return;
    const save = document.getElementById("rule-dialog-save");
    const error = document.getElementById("rule-dialog-error");
    error.textContent = "";
    save.disabled = true;
    try {
      const response = await fetch(api(`/api/transactions/${ruleSource.id}/rules`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pattern: document.getElementById("rule-dialog-pattern").value.trim(),
          field: document.getElementById("rule-dialog-field").value,
          category_id: Number(document.getElementById("rule-dialog-category").value),
          priority: Number(document.getElementById("rule-dialog-priority").value),
          apply_existing: document.getElementById("rule-dialog-apply").checked,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not save rule");
      document.getElementById("rule-dialog").close();
      document.getElementById("tx-rule-message").textContent =
        `Rule saved. Categorized ${result.updated} transaction(s).`;
      await loadTransactions();
      loadDashboard();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      save.disabled = false;
    }
  });

  document.getElementById("tx-refresh").addEventListener("click", () => {
    txOffset = 0;
    loadTransactions();
  });
  document.getElementById("tx-account").addEventListener("change", () => {
    txOffset = 0;
    loadTransactions();
  });
  document.getElementById("tx-prev").addEventListener("click", () => {
    txOffset = Math.max(0, txOffset - txLimit);
    loadTransactions();
  });
  document.getElementById("tx-next").addEventListener("click", () => {
    txOffset += txLimit;
    loadTransactions();
  });
  document.getElementById("tx-apply-rules").addEventListener("click", async () => {
    const res = await fetch(api(`/api/rules/apply`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ all: false }),
    }).then((r) => r.json());
    alert(`Categorized ${res.updated} transaction(s).`);
    loadTransactions();
    loadDashboard();
  });

  // -------------------------------------------------------- import/export --
  document.getElementById("import-btn").addEventListener("click", async () => {
    const fileInput = document.getElementById("import-file");
    const resultBox = document.getElementById("import-result");
    if (!fileInput.files.length) {
      resultBox.textContent = "Please choose a file first.";
      return;
    }
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    const accountOverride = document.getElementById("import-account").value.trim();
    if (accountOverride) formData.append("account", accountOverride);
    resultBox.textContent = "Importing...";
    try {
      const res = await fetch(api(`/api/import`), { method: "POST", body: formData }).then((r) => r.json());
      if (res.error) {
        resultBox.textContent = `Error: ${res.error}`;
      } else {
        resultBox.textContent =
          `Imported ${res.inserted} new transaction(s), skipped ${res.duplicates} duplicate(s) ` +
          `out of ${res.total_parsed} parsed.`;
        await loadAccounts();
        loadDashboard();
      }
    } catch (err) {
      resultBox.textContent = `Error: ${err}`;
    }
  });

  document.getElementById("export-btn").addEventListener("click", () => {
    const from = document.getElementById("export-from").value;
    const to = document.getElementById("export-to").value;
    const qs = new URLSearchParams();
    const account = document.getElementById("export-account").value;
    if (account) qs.set("account", account);
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);
    window.location.href = api(`/api/export?${qs}`);
  });

  // ---------------------------------------------------- categories/rules --
  async function loadCategoriesAndRules() {
    categories = await fetch(api(`/api/categories`)).then((r) => r.json());
    await loadCategoryOptionsForFilter();

    const catTbody = document.querySelector("#categories-table tbody");
    catTbody.innerHTML = "";
    categories.forEach((c) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${c.name}</td>
        <td>${c.type}</td>
        <td><span class="cat-badge" style="background:${c.color}">&nbsp;&nbsp;&nbsp;</span></td>
        <td class="row-actions"><button class="danger" data-id="${c.id}">Delete</button></td>
      `;
      tr.querySelector(".danger").addEventListener("click", async () => {
        if (!confirm(`Delete category "${c.name}"? Transactions keep their data but lose this category.`)) return;
        await fetch(api(`/api/categories/${c.id}`), { method: "DELETE" });
        loadCategoriesAndRules();
      });
      catTbody.appendChild(tr);
    });

    const ruleCategorySelect = document.getElementById("new-rule-category");
    ruleCategorySelect.innerHTML = "";
    categories.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      ruleCategorySelect.appendChild(opt);
    });

    const rules = await fetch(api(`/api/rules`)).then((r) => r.json());
    const ruleTbody = document.querySelector("#rules-table tbody");
    ruleTbody.innerHTML = "";
    rules.forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${r.pattern}</td>
        <td>${r.field}</td>
        <td>${r.category_name}</td>
        <td>${r.priority}</td>
        <td class="row-actions"><button class="danger" data-id="${r.id}">Delete</button></td>
      `;
      tr.querySelector(".danger").addEventListener("click", async () => {
        await fetch(api(`/api/rules/${r.id}`), { method: "DELETE" });
        loadCategoriesAndRules();
      });
      ruleTbody.appendChild(tr);
    });
  }

  document.getElementById("add-category").addEventListener("click", async () => {
    const name = document.getElementById("new-cat-name").value.trim();
    const type = document.getElementById("new-cat-type").value;
    const color = document.getElementById("new-cat-color").value;
    if (!name) return;
    await fetch(api(`/api/categories`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, type, color }),
    });
    document.getElementById("new-cat-name").value = "";
    loadCategoriesAndRules();
  });

  document.getElementById("add-rule").addEventListener("click", async () => {
    const pattern = document.getElementById("new-rule-pattern").value.trim();
    const field = document.getElementById("new-rule-field").value;
    const category_id = Number(document.getElementById("new-rule-category").value);
    const priority = Number(document.getElementById("new-rule-priority").value || 100);
    if (!pattern || !category_id) return;
    await fetch(api(`/api/rules`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pattern, field, category_id, priority }),
    });
    document.getElementById("new-rule-pattern").value = "";
    loadCategoriesAndRules();
  });

  // --------------------------------------------------------------- init --
  (async function init() {
    categories = await fetch(api(`/api/categories`)).then((r) => r.json());
    await loadCategoryOptionsForFilter();
    await loadAccounts();
    loadDashboard();
  })();
})();
