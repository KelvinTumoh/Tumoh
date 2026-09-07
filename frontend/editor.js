/* global require, monaco, Terminal, FitAddon */

require.config({
  paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs" },
});

const WS_URL = (() => {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
})();
const DOC_URI = "file:///project/main.py";
const LANGUAGE_ID = "python";
const INITIAL_CONTENT = "# Start typing...\n";

require(["vs/editor/editor.main"], function () {
  const editor = monaco.editor.create(document.getElementById("editor"), {
    value: INITIAL_CONTENT,
    language: LANGUAGE_ID,
    theme: "vs-dark",
    automaticLayout: true,
  });
  const model = editor.getModel();

  const diffEditor = monaco.editor.createDiffEditor(
    document.getElementById("diff-editor"),
    { theme: "vs-dark", automaticLayout: true }
  );

  let term = null;
  let fitAddon = null;

  if (typeof Terminal !== "undefined" && typeof FitAddon !== "undefined") {
    term = new Terminal({
      theme: { background: "#1e1e1e", foreground: "#d4d4d4" },
      cursorBlink: true,
    });
    term.open(document.getElementById("terminal"));
    fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    fitAddon.fit();
  } else {
    console.warn("xterm.js or xterm-addon-fit not loaded; skipping terminal.");
  }

  const ws = new WebSocket(WS_URL);
  let isRemoteUpdate = false;
  let completionId = 0;
  const pendingCompletions = new Map();

  ws.addEventListener("open", () => {
    ws.send(
      JSON.stringify({
        type: "doc_open",
        uri: DOC_URI,
        language_id: LANGUAGE_ID,
        content: model.getValue(),
      })
    );
    ws.send(JSON.stringify({ type: "get_tree" }));
    ws.send(JSON.stringify({ type: "get_project" }));
    ws.send(JSON.stringify({ type: "git_status" }));
  });

  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);

    switch (msg.type) {
      case "doc_sync":
        if (msg.uri === DOC_URI) {
          isRemoteUpdate = true;
          model.setValue(msg.text);
          isRemoteUpdate = false;
        }
        break;

      case "diagnostics":
        if (msg.uri === DOC_URI) {
          monaco.editor.setModelMarkers(
            model,
            "lsp",
            (msg.diagnostics || []).map((d) => markerFromDiagnostic(d))
          );
        }
        break;

      case "completions":
        const resolve = pendingCompletions.get(msg.request_id);
        if (resolve) {
          pendingCompletions.delete(msg.request_id);
          resolve(msg.items || []);
        }
        break;

      case "pty_output":
        if (term) term.write(msg.data);
        break;

      case "tree":
        renderTree(msg.tree);
        break;

      case "project_info":
        renderProjectInfo(msg);
        break;

      case "git_status":
        renderGitStatus(msg.status || []);
        break;

      case "git_diff":
        showDiff(msg.original || "", msg.modified || "");
        break;

      case "error":
        console.error("Server error:", msg.message);
        break;
    }
  });

  model.onDidChangeContent((event) => {
    if (isRemoteUpdate) return;

    for (const change of event.changes) {
      const start = model.getOffsetAt(change.range.getStartPosition());
      const end = model.getOffsetAt(change.range.getEndPosition());
      ws.send(
        JSON.stringify({
          type: "doc_edit",
          uri: DOC_URI,
          start_index: start,
          end_index: end,
          new_text: change.text,
        })
      );
    }
  });

  monaco.languages.registerCompletionItemProvider(LANGUAGE_ID, {
    provideCompletionItems: async function (_model, position) {
      const offset = model.getOffsetAt(position);
      const requestId = ++completionId;

      const promise = new Promise((resolve) => {
        pendingCompletions.set(requestId, resolve);
      });

      ws.send(
        JSON.stringify({
          type: "completion",
          uri: DOC_URI,
          offset: offset,
          request_id: requestId,
        })
      );

      const items = await promise;
      return {
        suggestions: items.map((item) => ({
          label: item.label,
          insertText: item.insertText || item.label,
          kind: item.kind || monaco.languages.CompletionItemKind.Text,
          detail: item.detail || "",
        })),
      };
    },
  });

  if (term) {
    term.onData((data) => {
      ws.send(JSON.stringify({ type: "pty_input", data }));
    });
  }

  // Workbench shell in workbench.js now owns tab and panel switching.
  window.addEventListener("resize", () => {
    editor.layout();
    diffEditor.layout();
  });

  function markerFromDiagnostic(d) {
    const severities = [8, 4, 2, 1];
    return {
      startLineNumber: d.range.start.line + 1,
      startColumn: d.range.start.character + 1,
      endLineNumber: d.range.end.line + 1,
      endColumn: d.range.end.character + 1,
      message: d.message,
      severity: severities[(d.severity || 1) - 1] || 8,
    };
  }

  function renderTree(node, parent = document.getElementById("file-tree")) {
    parent.innerHTML = "";
    const container = document.createElement("div");
    container.className = "tree-node";
    container.textContent = (node.type === "directory" ? "📁 " : "📄 ") + node.name;
    parent.appendChild(container);

    if (node.children && node.children.length) {
      const childContainer = document.createElement("div");
      childContainer.style.paddingLeft = "0.75rem";
      for (const child of node.children) {
        renderTree(child, childContainer);
      }
      parent.appendChild(childContainer);
    }
  }

  function renderProjectInfo(info) {
    const container = document.getElementById("project-info");
    const env = Object.keys(info.environment || {}).join(", ") || "none";
    const git = info.git && info.git.installed
      ? `${info.git.changes.length} change(s)`
      : "not a git repo";
    container.innerHTML = `<div>Tools: ${env}</div><div>Git: ${git}</div>`;
  }

  function renderGitStatus(status) {
    const container = document.getElementById("git-status");
    container.innerHTML = "";
    status.forEach((entry) => {
      const row = document.createElement("div");
      row.className = "git-entry";
      row.innerHTML = `<span class="git-status">${entry.status}</span><span>${entry.path}</span>`;
      row.addEventListener("click", () => {
        ws.send(JSON.stringify({ type: "git_diff", path: entry.path }));
        document.getElementById("tab-diff").click();
      });
      container.appendChild(row);
    });
  }

  function showDiff(original, modified) {
    const originalModel = monaco.editor.createModel(original, LANGUAGE_ID);
    const modifiedModel = monaco.editor.createModel(modified, LANGUAGE_ID);
    diffEditor.setModel({ original: originalModel, modified: modifiedModel });
  }
});
