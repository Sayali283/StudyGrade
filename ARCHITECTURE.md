# 🏛️ StudyGrade System Architecture & Engineering Guide

## 1. Directory Structure

```text
StudyGrade/
├── core/                           # Primary Django domain application
│   ├── api/                        # RESTful API layer (v1)
│   │   ├── __init__.py
│   │   ├── urls.py                 # /api/v1/ routing
│   │   └── views.py                # Standardized JSON endpoints
│   ├── services/                   # Domain & Business logic (Independent of HTTP/views)
│   │   ├── __init__.py             # Unified service exports
│   │   ├── document_service.py     # Multi-format document parser (PDF, DOCX, TXT, MD)
│   │   ├── quiz_service.py         # AI generation & NLP cloze fallback, scoring
│   │   ├── flashcard_service.py    # AI synthesis & recall card extraction
│   │   ├── streak_service.py       # Active study day & consecutive streak tracking
│   │   └── analytics_service.py    # Topic-level accuracy & weakness detection
│   ├── views/                      # Modular HTTP Request Handlers
│   │   ├── __init__.py             # Backward-compatible view exports
│   │   ├── auth_views.py           # Registration, login, logout
│   │   ├── notes_views.py          # Uploads, secure streaming, deletion
│   │   ├── quiz_views.py           # Quiz center, question taking, result reviews
│   │   ├── flashcard_views.py      # Deck management, interactive study session
│   │   ├── pomodoro_views.py       # Ambient focus timer studio
│   │   └── dashboard_views.py      # Student & parent dashboards, progress
│   ├── templates/                  # Presentation layer
│   │   ├── components/             # Reusable UI partials
│   │   │   ├── navbar.html         # Header & responsive navigation
│   │   │   ├── footer.html         # Standard footer
│   │   │   ├── messages.html       # Dismissible notification banners
│   │   │   ├── student_sidebar.html# Student portal navigation
│   │   │   └── parent_sidebar.html # Parent portal navigation
│   │   ├── 404.html                # Friendly not-found error page
│   │   ├── 500.html                # Standalone internal server error page
│   │   └── ... (page templates)
│   ├── forms.py                    # Form definitions
│   ├── models.py                   # Relational database models
│   ├── tests.py                    # Automated test suite (19 unit/integration tests)
│   ├── urls.py                     # Web route mappings
│   └── utils.py                    # Formatting and utility helpers
├── smartstudy/                     # Project configuration
│   ├── settings.py                 # Decoupled environment settings
│   ├── urls.py                     # Root URL router (mounts /api/v1/ and /)
│   └── wsgi.py                     # Production WSGI application
├── media/                          # Uploaded files directory (protected)
├── static/                         # Static CSS/JS assets
├── staticfiles/                    # Compiled static assets for WhiteNoise
├── .env.example                    # Environment variable template
├── Procfile                        # Production process declaration (gunicorn)
├── requirements.txt                # Production dependencies
└── runtime.txt                     # Target Python runtime
```

---

## 2. Separation of Concerns (Three-Tier Architecture)

1. **Presentation Layer (`core/templates/` & `core/views/`)**:
   - Views are strictly responsible for HTTP protocol concerns: extracting request parameters, performing authentication checks, delegating to services, and returning appropriate HTTP or JSON responses.
   - UI components are separated into reusable partials inside `templates/components/`.

2. **Service / Business Logic Layer (`core/services/`)**:
   - Contains pure business rules and data transformations.
   - Contains zero HTTP dependencies; services can be invoked from views, API controllers, Celery background tasks, or management commands.

3. **Data Access Layer (`core/models.py`)**:
   - Defines relational schemas for Students, Parents, Notes, Quizzes, Questions, Answers, Flashcards, and Study Days.

---

## 3. Scalable RESTful API (`/api/v1/`)

All endpoints return a standardized JSON envelope:
- **Success:** `{"status": "success", "message": "...", "data": {...}}`
- **Error:** `{"status": "error", "code": "ERROR_CODE", "message": "..."}`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health/` | Public health check probe |
| `GET` | `/api/v1/streak/` | Authenticated student study streak |
| `GET` | `/api/v1/analytics/` | Topic accuracy and recommended review areas |
| `POST` | `/api/v1/pomodoro/complete/` | Log a completed focus block |
| `GET` | `/api/v1/notes/` | List notes for authenticated student |
| `GET` | `/api/v1/notes/<id>/flashcards/` | Retrieve flashcards for a specific note |

---

## 4. State Management Strategy

- **Server-Side Session State:** Managed via Django authentication sessions (`auth.User`, `Student`, `Parent`).
- **Timer & Focus State:** Client-side persistence using namespaced `localStorage` key (`studyGuardPomodoro-<userId>`), supporting session continuity across page reloads.
- **Flashcard Study State:** Ephemeral deck state tracks mastered cards, card flipping, and progress in-memory with real-time UI counters.

---

## 5. Security & Authorization

- **Media Protection:** Note files are streamed via `view_note` requiring explicit ownership checks (owner student or linked parent).
- **IDOR Protection:** Quiz attempts and test generation validate `student=request.user.student`.
- **CSRF Defense:** `CSRF_TRUSTED_ORIGINS` configured for HTTPS domains, form tokens required for all state-changing endpoints.
