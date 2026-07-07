# 摩尚OA — Domain Context

> This glossary defines the canonical business terms. Implementation decisions live in `docs/adr/`. Keep this file free of code, APIs, and architecture.

## Bounded Context

**摩尚OA** is a desktop application for a small law firm (摩尚律师事务所). It wraps the firm's existing cloud OA system (`moshang2.ycq6.com`) into a purpose-built native client for daily operations: filing cases, reviewing pending approvals, and downloading generated legal documents.

## Users

| Term | Definition |
|------|-----------|
| **承办律师** (Handling Lawyer) | A licensed lawyer at the firm who files cases, downloads documents, and manages their own caseload. The primary daily user. |
| **审批人** (Approver) | A partner-level lawyer who reviews and approves/rejects pending case filings before they become official. A single person may be both Handling Lawyer and Approver. |

The application serves 2–3 concurrent users. There is no admin role distinct from these two.

## Core Concepts

| Term | Definition |
|------|-----------|
| **案件** (Case) | A legal engagement tracked in the OA. Has a type (civil 民事 or criminal 刑事), a normative cause/charge, parties, handling lawyers, fee terms, and a lifecycle status. |
| **立案** (Case Filing) | The act of registering a new Case in the OA, including all required fields: parties, cause, court, lawyers, fee method, authorization type. |
| **立案审批** (Filing Approval) | A gate where an Approver reviews a newly filed Case before it becomes active. Includes automated pre-checks (completeness, conflict of interest, duplicate filing). |
| **利冲检索** (Conflict Check) | An automated search that detects whether the parties in a new filing conflict with existing cases in the firm — same party appearing on opposing sides. |
| **文书** (Legal Document) | Generated documents bound to a Case: engagement letters (委托书), powers of attorney (授权委托书), etc. Downloaded from the OA. |
| **案由** (Cause of Action) | The normative legal classification of a civil Case, selected from the OA dictionary — not free text. |
| **罪名** (Criminal Charge) | The normative charge for a criminal Case, selected from the OA dictionary. |
| **收费方案 / 收费说明** (Fee Scheme) | Free-text description of how the case fee is structured (e.g. upfront amount + percentage of recovery), stored in the OA. One field serves both purposes: it is the fee *scheme* reviewed for risk-fee cases and the fee *explanation* required for low-fee cases. |
| **低收费审查** (Low-Fee Review) | An approval gate rule: any case with an entrusted fee below ¥5,000 must have a Fee Scheme on file, otherwise it cannot pass Filing Approval. |
| **风险代理** (Contingency/Risk Fee) | A fee arrangement contingent on case outcome, regulated by 司发通〔2021〕87号: prohibited for certain case types, capped by a graduated percentage of the subject amount. The system renders a preliminary compliance judgment; the Approver makes the final call. |
| **API Key** | A per-user credential issued by the OA backend. Used to authenticate and obtain a session token. Each user has their own key. |
| **Token** | A temporary session credential obtained by exchanging an API Key. All subsequent OA requests use this token. |

## Out of Scope (not in this application)

- **录屏取证** (Screen Recording Evidence) — lives in the separate 案件看板 tool.
- **飞书多维表格** — the firm's Feishu tables are a separate data system; this app only talks to the OA.
- **结案审批** (Case Closure Approval) — the OA API for closure approval is unverified; deferred to a future version.
- **收费管理** (Fee Management) — read-only financial overview may appear later; no write operations planned.
- **团队管理** (Team Management) — not in scope.
