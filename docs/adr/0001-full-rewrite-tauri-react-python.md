# ADR-0001: Full Rewrite with Tauri + React + FastAPI

## Status

Accepted (2026-07-08) — Amended same day: desktop shell is **pywebview**, not Tauri (see Amendment below)

## Context

The existing 摩尚OA desktop app (Tauri 3 + React 19) has accumulated several problems:

1. **Visual design** — the gold-and-ink "law firm stationery" theme feels dated; the team wants a modern SaaS aesthetic (Linear/Notion style).
2. **Usability** — case filing is a single overloaded form instead of a guided wizard; the approval module is incomplete in the frontend; navigation is cramped.
3. **Architecture** — OA integration logic is split between Rust sidecar calls and Python scripts in the skill directory. The Rust layer does process management and JSON parsing that adds complexity without adding value, since the real OA logic (conflict events, SaveChangesV2 repair, field normalization) all lives in Python.

A partial refactor (keep Rust/sidecar, redo React) was considered but rejected: the team chose a full rewrite to shed the split-brain architecture.

## Decision

Rebuild the application from scratch with:

- **Tauri 3** as the desktop shell (window management, process lifecycle, native menus)
- **React** (latest) + **Tailwind CSS** for the frontend, modern SaaS visual style
- **FastAPI (Python)** as a local backend process that Tauri spawns and manages

The FastAPI backend wraps the existing skill Python scripts (login, case query, filing, approval, document download) as HTTP endpoints. The frontend talks to `localhost:<port>`, not to Tauri Rust commands. This means:

- All OA integration logic stays in Python — no Rust reimplementation.
- The frontend is a standard SPA that can later be deployed as a web app by moving the FastAPI backend to a server.
- Tauri's role is minimal: spawn the Python process, open the window, done.

## Consequences

- **Positive**: Python OA scripts (conflict check, SaveChangesV2 repair, field normalization) are reused nearly verbatim. Web-化 path is straightforward. Single language for all business logic.
- **Negative**: End users need Python bundled with the app (or we embed a Python runtime in the Tauri bundle). The app is larger than a pure-Rust build.
- **Risk**: If Python bundling proves too fragile for distribution to 2-3 non-technical users, we may fall back to a "start.sh" launch script model (like the photo-picker tool).

## Amendment (2026-07-08)

During implementation we found the machine's Rust toolchain had been removed
(`rustup` lists no toolchains), so building a Tauri shell would require a
GB-scale toolchain download plus a long first compile. Since the backend is
already Python, the shell was implemented with **pywebview** instead: `backend/desktop.py`
starts uvicorn and opens a native WKWebView window; `启动摩尚OA.command` is the
double-click launcher. Everything else in this ADR (React frontend, FastAPI
backend, web-deployable architecture) is unchanged. Tauri remains the upgrade
path if we later want signed .dmg installers for distribution.
