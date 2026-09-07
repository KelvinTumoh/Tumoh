/* Professional workbench shell controller. */

(function () {
  "use strict";

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

  function setActive(items, target, activeClass = "active") {
    items.forEach((el) => el.classList.remove(activeClass));
    target.classList.add(activeClass);
  }

  function showSidebarView(viewId) {
    $$(".sidebar-view").forEach((el) => el.classList.add("hidden"));
    const view = document.getElementById(viewId);
    if (view) view.classList.remove("hidden");
  }

  function initActivityBar() {
    const buttons = $$(".activity-btn");
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        setActive(buttons, btn);
        showSidebarView(btn.dataset.view);
      });
    });
  }

  function initTabs() {
    const tabs = $$("#tab-bar .tab");
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        setActive(tabs, tab);
        const viewId = tab.dataset.view;
        $$("#editor-area > .view").forEach((el) => {
          el.classList.toggle("hidden", el.id !== viewId);
        });
      });
    });
  }

  function initPanelTabs() {
    const tabs = $$("#panel-header .panel-tab");
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        setActive(tabs, tab);
        const panelId = tab.dataset.panel;
        $$("#panel-body > .panel").forEach((el) => {
          el.classList.toggle("hidden", el.id !== panelId);
        });
      });
    });
  }

  function updateStatusBar(text) {
    const el = $("#status-message");
    if (el) el.textContent = text;
  }

  function initStatusBar() {
    const lang = $("#status-language");
    if (lang) lang.textContent = "Python";
    updateStatusBar("Ready");
  }

  document.addEventListener("DOMContentLoaded", () => {
    initActivityBar();
    initTabs();
    initPanelTabs();
    initStatusBar();
  });

  window.workbench = {
    updateStatusBar,
    showSidebarView,
  };
})();
