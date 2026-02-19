# Admin Panel — Content Service

UI/UX specification for the admin panel surfaces driven by the content microservice.
Covers every screen, layout, component, and the API gaps that need to be filled
before each screen can be built.

---

## Table of Contents

1. [Content Moderation](#content-moderation)
   - [Reports Queue](#1-reports-queue)
   - [Flagged Content Feed](#2-flagged-content-feed)
   - [Post Visibility Override](#3-post-visibility-override)
2. [Editor Picks](#editor-picks)
   - [Editor Picks Board](#4-editor-picks-board)
3. [Feed Experiments](#feed-experiments)
   - [Cohorts List](#5-cohorts-list)
   - [Create / Edit Cohort Form](#6-create--edit-cohort-form)
   - [Experiments List](#7-experiments-list)
   - [Create Experiment Form](#8-create-experiment-form)
   - [Experiment Detail & Results](#9-experiment-detail--results)
4. [Search Index Management](#search-index-management)
   - [OpenSearch Index Health](#10-opensearch-index-health)
5. [Post & Channel Management](#post--channel-management)
   - [Posts Browser](#11-posts-browser)
   - [Channels Browser](#12-channels-browser)
6. [Analytics Overview](#analytics-overview)
   - [Feed Performance Dashboard](#13-feed-performance-dashboard)
7. [Global UX Patterns](#global-ux-patterns)
8. [Missing API Endpoints](#missing-api-endpoints-needed-before-building)

---

## Content Moderation

### 1. Reports Queue

The daily driver for trust & safety. This is the highest-priority screen.
Think Jira-style ticket queue — one report at a time, actionable in place.

**Layout:** Split-panel — queue list on the left, report detail on the right.

---

**Left panel — Queue**

Filter tabs at the top:
```
[ All ] [ Open ] [ Reviewed ] [ Actioned ] [ Dismissed ]
```

Secondary filter row:
```
Target type:  [ All ▾ ]  [ Post ]  [ Comment ]  [ User ]  [ Webinar ]
Sort:         [ Newest first ▾ ]  [ Most reported first ]
```

Each row in the queue:

```
┌────────────────────────────────────────────────────────┐
│ 🔴 5 reports   POST                        2h ago      │
│ "The role of statins in acute coronary..."             │
│ Reason: Misinformation                                 │
└────────────────────────────────────────────────────────┘
```

- Red badge when report count ≥ 5 — the auto-hide threshold has already
  triggered. Admin needs to explicitly confirm or reinstate.
- Clicking a row loads the detail panel without a page reload.

---

**Right panel — Detail**

```
┌─────────────────────────────────────────────────────────────┐
│  POST  ·  HIDDEN_BY_ADMIN (auto-hidden)                     │
│  ⚠️  This post was auto-hidden due to 5+ reports.           │
│     Confirm hide or reinstate it.                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Rendered post content — exactly as users see it]         │
│                                                             │
│  Author: <user_id>   ·   Published: Feb 14, 2026           │
│  Likes: 12  ·  Comments: 3  ·  Shares: 1                   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Reports (5)                                                │
│  ──────────────────────────────────────────────────────    │
│  user_abc  ·  Misinformation  ·  Feb 14 09:12              │
│  user_def  ·  Misinformation  ·  Feb 14 09:45              │
│  user_ghi  ·  Spam            ·  Feb 14 10:03              │
│  user_jkl  ·  Inappropriate   ·  Feb 14 11:20              │
│  user_mno  ·  Misinformation  ·  Feb 14 12:01              │
├─────────────────────────────────────────────────────────────┤
│  Action note (optional):  [_________________________________]│
│                                                             │
│  [ Keep Live ]   [ Confirm Hide ]   [ Soft Delete ]        │
└─────────────────────────────────────────────────────────────┘
```

Button behaviour:
- **Keep Live** → PATCH reports to `DISMISSED`, restore post to `PUBLISHED`/`EDITED`
- **Confirm Hide** → PATCH reports to `ACTIONED`, leave post as `HIDDEN_BY_ADMIN`
- **Soft Delete** → DELETE post + PATCH reports to `ACTIONED`

`reviewed_by` is auto-filled from the admin's JWT. `action_taken` maps to the note field.

Keyboard shortcuts for high-volume sessions:
- `K` = Keep Live
- `H` = Confirm Hide
- `D` = Soft Delete
- `N` = Next report in queue

---

### 2. Flagged Content Feed

A secondary moderation surface for bulk review sessions — browsing all
`HIDDEN_BY_ADMIN` content in one place rather than working through the queue.

**Layout:** Full-width card feed, infinite scroll.

Each card:
```
┌──────────────────────────────────────────────────────────┐
│  [Post content preview — truncated to ~200 chars]        │
│                                                          │
│  Author: <id>  ·  Hidden: Feb 14  ·  Reports: 5         │
│  Status: HIDDEN_BY_ADMIN                                 │
│                                                          │
│  [ Reinstate ]   [ Confirm Hide ]   [ Delete ]           │
└──────────────────────────────────────────────────────────┘
```

Bulk action bar appears when items are checked:
```
☑ 12 selected   [ Dismiss All Reports ]  [ Confirm Hide All ]  [ Delete All ]
```

Filter bar:
```
Hidden after: [date picker]    Content type: [dropdown]    Search by author ID: [text]
```

---

### 3. Post Visibility Override

Direct post lookup — used when a specific post ID or author is reported
externally (e.g., via email complaint) rather than through the in-app report flow.

**Layout:** Search bar at top, result below.

Search:
```
Find post:  [ post ID or keyword ________________________ ]  [ Search ]
```

Post detail (same rendered view as reports queue) plus:

**Version history timeline:**
```
v4  Feb 19, 2026  "Edited by author"          [ Restore ]
v3  Feb 18, 2026  "Edited by author"          [ Restore ]
v2  Feb 14, 2026  "Edited by author"          [ Restore ]
v1  Feb 10, 2026  "Original"                  (current)
```

Actions at the top:
```
[ Force Hide ]   [ Restore to Published ]   [ Soft Delete ]
```

Show current status, visibility setting, content type, version number, and
all timestamps prominently so the admin has full context before acting.

---

## Editor Picks

### 4. Editor Picks Board

A curation surface for managing the 20% cold-start bucket and the
`GET /feed/editor-picks` endpoint. Think of it as a ranked playlist.

**Layout:** Drag-and-drop ranked list.

```
Editor Picks  (14 active)                        [ + Add Post ]

  ⠿  1.  Cardiology Basics                  Dr. Smith  ·  Feb 12  ·  ❤️ 45   Active ●
  ⠿  2.  New Guidelines for Hypertension    Dr. Lee    ·  Feb 10  ·  ❤️ 82   Active ●
  ⠿  3.  Interpreting ECGs                  Dr. Patel  ·  Feb 08  ·  ❤️ 23   Active ●
  ⠿  4.  [POST HIDDEN — no longer live]                                       ⚠️    [ Remove ]
  ⠿  5.  Understanding MRI Reports          Dr. Wu     ·  Feb 05  ·  ❤️ 67   Active ●
```

- Drag handle (⠿) on the left to reorder — maps to `priority` column.
- `Active ●` toggle to show/hide from feed without removing from list.
- Warning badge on any post that has been soft-deleted, hidden, or unpublished
  since it was added — the admin needs to curate it out manually.
- `[ + Add Post ]` opens a search modal:

```
┌─────────────────────────────────────────┐
│  Add to Editor Picks                    │
│                                         │
│  Search: [_____________________________]│
│                                         │
│  > Cardiology update Feb 2026           │
│  > New statin guidelines...             │
│  > ECG interpretation guide...          │
│                                         │
│  [ Cancel ]               [ Add Post ]  │
└─────────────────────────────────────────┘
```

---

## Feed Experiments

### 5. Cohorts List

Table view of all cohorts. This is read-heavy; writes happen in the form.

```
Cohorts                                             [ + Create Cohort ]

 Name              Priority  Active  Algorithm (r / s / a)  Created By  Actions
 ─────────────────────────────────────────────────────────────────────────────
 Cardiologists         1       ●      0.4 / 0.3 / 0.3       admin       Edit  Delete
 New Users (< 30d)     2       ●      0.5 / 0.3 / 0.2       admin       Edit  Delete
 Power Users           3       ●      0.3 / 0.2 / 0.5       admin       Edit  Delete
 India — Tier 2        4       ○      0.4 / 0.4 / 0.2       admin       Edit  Delete
```

- Priority column is editable inline (number input or drag-to-reorder row).
- `Active` toggle directly in the table row — no need to open the form.
- Lower priority number = higher precedence when a user belongs to multiple cohorts.
  Show a tooltip explaining this wherever priority is displayed.

---

### 6. Create / Edit Cohort Form

Two-column layout. Left: identity & rules. Right: algorithm config live preview.

**Left — Identity**

```
Name *          [_________________________________]
Description     [_________________________________]
                [_________________________________]
Priority *      [ 1  ]   ← lower = higher precedence
Active          [●  On ]
```

**Left — Segment Rules (reference only — membership resolved externally)**

Key-value rule builder:

```
Rules  (used for documentation — not evaluated by content service)

 Type          Value                       [ + Add Rule ]
 ─────────────────────────────────────────────────────
 Specialty  ▾  Cardiology                  [ × ]
 Geography  ▾  India                       [ × ]
 Behaviour  ▾  signup_days_lt_30           [ × ]
```

**Right — Feed Algorithm Config**

```
Feed Algorithm Weights

  Recency    [━━━━━●━━━━━] 0.40
  Specialty  [━━━━●━━━━━━] 0.30
  Affinity   [━━━━●━━━━━━] 0.30
                           ─────
             Total:        1.00  ✓

  Cold-start threshold   [ 10 ] interactions
  Affinity ceiling       [ 50 ] points

  ⓘ Users below the cold-start threshold see
    20% editor picks / 40% trending / 40% specialty
    regardless of these weights.
```

- Live sum indicator — warn in red if weights don't add up to 1.0.
- Show a mini feed score example to make the weights tangible:
  "A post published 12h ago by a followed cardiologist would score ~0.72"

---

### 7. Experiments List

Table with status colour-coding.

```
Experiments                                         [ + Create Experiment ]

Filter:  [ All ▾ ]  [ DRAFT ]  [ RUNNING ]  [ PAUSED ]  [ COMPLETED ]
Cohort:  [ All ▾ ]

 Name                   Cohort          Status      Variants  Start      End        Actions
 ─────────────────────────────────────────────────────────────────────────────────────────
 Recency Boost Test      Cardiologists  🟢 RUNNING   A / B     Feb 10     Mar 10     View · Pause
 Affinity Weight v2      Power Users    🟡 PAUSED    A / B     Jan 15     Feb 15     View · Resume
 Cold-start Threshold    New Users      ⚪ DRAFT      A / B / C  —          —         View · Start
 Q4 Specialty Test       All Users      ⚫ COMPLETED  A / B     Dec 01     Dec 31     View Results
```

Status colours: 🟢 RUNNING · 🟡 PAUSED · ⚪ DRAFT · ⚫ COMPLETED

---

### 8. Create Experiment Form

Three sections. Validation is enforced in the UI before the API call.

**Section 1 — Basic Info**

```
Name *           [_________________________________]
Description      [_________________________________]
Cohort *         [ Cardiologists              ▾ ]
Start date       [ Feb 20, 2026  📅 ]
End date         [ Mar 20, 2026  📅 ]

ⓘ Minimum duration: 7 days
```

**Section 2 — Variants**

```
Variants                                           [ + Add Variant ]

 ┌──────────────────────────────────────────────────────────────┐
 │ Variant A  (Control)                                         │
 │ Traffic  [ 50 ]%                                             │
 │                                                              │
 │ Algorithm override:                                          │
 │   Recency    [━━━━━●━━━━━] 0.40                             │
 │   Specialty  [━━━━●━━━━━━] 0.30                             │
 │   Affinity   [━━━━●━━━━━━] 0.30                             │
 └──────────────────────────────────────────────────────────────┘

 ┌──────────────────────────────────────────────────────────────┐
 │ Variant B                                           [ Remove ]│
 │ Traffic  [ 50 ]%                                             │
 │                                                              │
 │ Algorithm override:                                          │
 │   Recency    [━━━━━━━●━━━] 0.60                             │
 │   Specialty  [━━━●━━━━━━━] 0.20                             │
 │   Affinity   [━━━●━━━━━━━] 0.20                             │
 └──────────────────────────────────────────────────────────────┘

 Traffic total:  100%  ✓
```

Rules:
- Minimum 2 variants.
- Traffic percentages must sum exactly to 100 — show live counter, disable Save if not.
- First variant defaults to "Control" label (convention only, not enforced in DB).
- Per-variant weight sliders are pre-filled from the selected cohort's defaults.

---

### 9. Experiment Detail & Results

The richest screen. Three sections: header, lifecycle controls, results.

**Header**

```
Recency Boost Test                                   🟢 RUNNING
Cohort: Cardiologists  ·  Feb 10 – Mar 10, 2026  ·  28 days remaining
```

**Lifecycle controls (context-aware)**

```
DRAFT    →  [ Start Experiment ]
RUNNING  →  [ Pause ]
PAUSED   →  [ Resume ]   [ Complete ]
COMPLETED → (read-only)
```

Clicking Start / Complete shows a confirmation modal:
```
Start this experiment?
This will begin serving variant B to 50% of Cardiologists.
Impressions will be tracked from this moment.
[ Cancel ]  [ Confirm Start ]
```

**Results section**

Refresh button top-right: `[ ↻ Refresh Results ]` — calls `GET /experiments/{id}/results`.

One card per variant, side by side:

```
┌──────────────────────────┐  ┌──────────────────────────┐
│ Variant A  (Control)     │  │ Variant B                │
│ 50% traffic              │  │ 50% traffic              │
│                          │  │                          │
│ Impressions   12,450     │  │ Impressions   12,380     │
│ CTR           3.8%       │  │ CTR           4.9%  ↑    │
│ 95% CI        3.4–4.2%   │  │ 95% CI        4.4–5.4%  │
│                          │  │                          │
│ Likes/session   1.9      │  │ Likes/session   2.4  ↑   │
│ Avg session     3m 42s   │  │ Avg session     4m 18s ↑ │
│                          │  │                          │
│                          │  │ ✅ Statistically         │
│                          │  │    significant vs A      │
└──────────────────────────┘  └──────────────────────────┘
```

Significance note below the cards:
```
Variant B's CTR confidence interval lower bound (4.4%)
exceeds Variant A's upper bound (4.2%).
Result is statistically significant at 95% confidence.
```

Event breakdown table (collapsible):

```
Event type      Variant A    Variant B
──────────────────────────────────────
Impressions      12,450       12,380
Clicks            473          607
Likes             890         1,021
Comments          134          189
Session starts   2,100        2,089
```

---

## Search Index Management

### 10. OpenSearch Index Health

A status dashboard for diagnosing search issues.

```
OpenSearch Health                              [ ↻ Refresh ]

Cluster status:   🟢 Green
Content index:    42,381 documents    Last indexed: Feb 19, 2026 14:23
User index:       0 documents         ⚠️  Never populated (identity service not integrated)

┌────────────────────────────────────────────────────┐
│  Reindex                                           │
│                                                    │
│  Bulk reindex all posts:   [ Reindex All Posts ]   │
│                                                    │
│  Single post:  [ post_id _____ ]  [ Reindex ]      │
└────────────────────────────────────────────────────┘

Recent indexing activity (last 20 events):
 Feb 19 14:23  post_abc123  INDEXED    success
 Feb 19 14:19  post_xyz789  DELETED    success
 Feb 19 13:55  post_def456  INDEXED    failed — connection timeout
```

Warnings shown automatically:
- User index at 0 documents → "People search will return no results until the identity service populates this index."
- Cluster status Yellow/Red → banner at top of page.

---

## Post & Channel Management

### 11. Posts Browser

Searchable, filterable table of **all** posts — including statuses not visible in the public feed.

**Filter bar:**

```
Status:        [ All ▾ ]  Draft  Published  Edited  Soft Deleted  Hidden
Content type:  [ All ▾ ]  Text  Image  Video  Link  Webinar  Course  Repost
Channel:       [ All ▾ ]
Author ID:     [ _________________________ ]
Date range:    [ From 📅 ]  [ To 📅 ]
               [ Search ]
```

**Table:**

```
 Title                        Author     Type    Status          Likes  Comments  Created      Actions
 ─────────────────────────────────────────────────────────────────────────────────────────────────────
 Cardiology update Feb 2026   user_abc   TEXT    PUBLISHED       45     12        Feb 14        View · Hide
 Understanding MRI             user_def   IMAGE   EDITED          23     4         Feb 10        View · Hide
 [Deleted post]                user_ghi   TEXT    SOFT_DELETED    —      —         Jan 30        Restore · Delete
 Spam post                     user_xyz   TEXT    HIDDEN_BY_ADMIN —      —         Jan 28        View · Restore
```

Clicking `View` opens the same post detail panel from the reports queue.

---

### 12. Channels Browser

```
Channels                                              [ + Create Channel ]

 Name                   Slug                 Owner       Posts  Active  Created     Actions
 ─────────────────────────────────────────────────────────────────────────────────────────
 Cardiology Today        cardiology-today     user_abc    142    ●       Jan 05      Edit · Deactivate · View Posts
 ECG Learning Hub        ecg-learning-hub     user_def    67     ●       Jan 12      Edit · Deactivate · View Posts
 Pharmacology Notes      pharmacology-notes   user_ghi    23     ○       Feb 01      Edit · Activate   · View Posts
```

- `Active` toggle inline.
- `View Posts` links to the Posts Browser pre-filtered to that channel.
- `Edit` opens an inline form: name, description, logo URL.
- `Deactivate` with confirmation modal — does not delete, just sets `is_active = false`.

---

## Analytics Overview

### 13. Feed Performance Dashboard

All data is derivable from existing DB tables — no new models needed.
These are aggregation queries over posts and experiment_events.

**Layout:** 2-column grid of metric cards + charts.

```
┌──────────────────────┐  ┌──────────────────────┐
│ Total live posts     │  │ Posts created today  │
│       42,381         │  │         127          │
└──────────────────────┘  └──────────────────────┘

┌──────────────────────┐  ┌──────────────────────┐
│ Open reports         │  │ Auto-hidden today    │
│          34          │  │           8          │
└──────────────────────┘  └──────────────────────┘
```

**Engagement by content type** (bar chart):

```
Average engagement score per post (last 30 days)
                                                     like + comment×2 + share×3
TEXT     ████████████████████  4.2
IMAGE    ████████████████████████████  6.8
VIDEO    ████████████████████████████████████  9.1
LINK     ████████  2.0
REPOST   ██████  1.5
```

**Top 10 posts this week** (table by engagement score):

```
 #   Title                              Author     Engagement  Views  CTR
 ─────────────────────────────────────────────────────────────────────
 1   Cardiology update Feb 2026          user_abc   92          1,240  7.4%
 2   New ECG guidelines                  user_def   87          980    8.9%
 ...
```

**Report volume over time** (line chart, 30 days):

```
Daily reports submitted  vs  Daily reports actioned
```

**Trending feed health:**

```
Trending cache:   🟢 Fresh  (last updated 3m ago)
Affinity cache:   🟢 Active (1,204 active keys in Redis)
Weight cache:     🟢 Active (89 active keys in Redis)
```

---

## Global UX Patterns

These conventions should apply to every screen.

| Pattern | Specification |
|---------|---------------|
| **Auth** | Admin login separate from user login. Admin JWT must carry a `role: admin` claim. Session timeout: 8 hours. |
| **Confirmation modals** | All destructive actions (Hide, Delete, Complete Experiment) require a one-sentence modal. No double-dialogs. Keep it short: "This will hide the post from all users." |
| **Audit trail** | Every moderation action displays "Actioned by X at Y" using `reviewed_by` + `action_taken` columns. Never show raw UUIDs — link to user lookup. |
| **Post previews** | Always render posts exactly as users see them (markdown, images, link previews). Raw JSON is never shown to moderators. |
| **Empty states** | Reports queue empty → "Nothing to review — last checked Feb 19, 14:23". Experiments list empty → "+ Create your first experiment". Never show a blank table. |
| **Pagination** | All tables use offset pagination (page 1, 2, 3…). Admins navigate by page number, not infinite scroll. Default page size: 25 rows. |
| **Status colours** | `PUBLISHED/ACTIVE/RUNNING` → green · `DRAFT/PAUSED` → yellow · `HIDDEN/SOFT_DELETED/COMPLETED` → grey · `AUTO_HIDDEN` → red |
| **Relative timestamps** | Show relative time ("2h ago") in lists; show absolute datetime ("Feb 19, 2026 14:23 UTC") in detail views. |
| **UUIDs** | Never show raw UUIDs to admins. Always show a short alias (first 8 chars) with a copy-to-clipboard icon. |
| **Mobile** | Reports queue and post browser should be usable on tablet. Experiment results and cohort forms are desktop-only (too dense). |

---

## Missing API Endpoints Needed Before Building

The content service needs these new admin-scoped endpoints.
None require architectural changes — they are additive.

| Screen | Missing endpoint | Notes |
|--------|-----------------|-------|
| Reports Queue | `GET /admin/reports` | Filters: `status`, `target_type`, `sort=count\|date`, pagination. Currently reports can only be created, not listed. |
| Reports Queue | `PATCH /admin/reports/bulk` | Bulk-action multiple report IDs (dismiss / action) in one call. |
| Flagged Content Feed | `GET /admin/posts?status=HIDDEN_BY_ADMIN` | The existing `GET /cms/my-posts` only returns the requester's posts. A full admin view needs a separate endpoint with no author filter. |
| Posts Browser | `GET /admin/posts` | All posts, all statuses, with full filter set (status, content_type, channel_id, author_id, date range). |
| Search Health | `POST /admin/search/reindex` | Trigger bulk re-index of all live posts into OpenSearch. Currently no endpoint — only BackgroundTask per individual post. |
| Search Health | `POST /admin/search/reindex/{post_id}` | Manual single-post re-index. |
| Analytics | `GET /admin/analytics/engagement` | Aggregated engagement by content type over N days. |
| Analytics | `GET /admin/analytics/reports` | Report submission counts per day over N days. |
| Experiments | `POST /admin/experiments/sweep` | Auto-complete all experiments whose `end_date` has passed. Designed to be called by a cron job. |
| Cohorts | `POST /experiments/cohorts/{id}/preview` | Dry-run: given a set of user attributes, return which cohort they would land in. Requires identity service integration. |

All endpoints above should require the `role: admin` claim in the JWT.
The existing service trusts the API gateway for this today — if RBAC is later
moved in-house, these endpoints are the ones to gate first.

---

*Last updated: 2026-02-19*
