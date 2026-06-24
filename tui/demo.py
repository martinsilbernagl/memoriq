"""Generate demo database with realistic fake data for TUI screenshots."""

import sqlite3
import uuid
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import sys
import random

# Reuse schema from init_db
sys.path.insert(0, str(Path.home() / ".memoriq" / "mcp-server"))


def create_demo_db(comprehensive: bool = True) -> str:
    """Create a temp DB with demo data. Returns path to temp DB.

    Args:
        comprehensive: If True, generate 50+ facts and extensive sample data
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="memoriq_demo_")
    db_path = tmp.name
    tmp.close()

    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")

    # Create minimal schema
    db.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            name TEXT PRIMARY KEY,
            path TEXT,
            dna TEXT,
            last_session TEXT
        );
        CREATE TABLE IF NOT EXISTS facts (
            id TEXT PRIMARY KEY,
            project TEXT,
            content TEXT NOT NULL,
            type TEXT DEFAULT 'fact',
            domain TEXT,
            tags TEXT,
            source_file TEXT,
            source_hash TEXT,
            session_id TEXT,
            timestamp TEXT,
            heat_score REAL DEFAULT 1.0,
            retrieval_count INTEGER DEFAULT 0,
            knowledge_tier TEXT DEFAULT 'active',
            cluster_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            project TEXT,
            start_time TEXT,
            end_time TEXT,
            summary TEXT,
            bridge_content TEXT,
            episode_title TEXT,
            episode_tags TEXT,
            outcome TEXT,
            facts_count INTEGER DEFAULT 0,
            changes_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            project TEXT,
            file_path TEXT,
            action TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS knowledge_gaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            query TEXT,
            hit_count INTEGER DEFAULT 0,
            best_score REAL DEFAULT 0.0,
            first_seen TEXT,
            last_seen TEXT,
            times_seen INTEGER DEFAULT 1,
            resolved INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS contradictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            fact_id_a TEXT,
            fact_id_b TEXT,
            reason TEXT,
            detected TEXT,
            resolved INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS fact_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            label TEXT,
            summary TEXT,
            fact_count INTEGER DEFAULT 0,
            created TEXT
        );
        CREATE TABLE IF NOT EXISTS fact_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_id_a TEXT,
            fact_id_b TEXT,
            relation TEXT,
            created TEXT
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            decision TEXT,
            reasoning TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS project_identity (
            project TEXT PRIMARY KEY,
            data TEXT
        );
        CREATE TABLE IF NOT EXISTS identity_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            field TEXT,
            old_value TEXT,
            new_value TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS tech_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT,
            stack TEXT
        );
        CREATE TABLE IF NOT EXISTS causal_chains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cause_fact_id TEXT,
            effect_fact_id TEXT,
            relation TEXT,
            created TEXT
        );
    """)

    now = datetime.now()
    random.seed(42)  # Reproducible

    # --- Projects ---
    projects = [
        ("my-saas-app", "~/projects/my-saas-app", "Next.js 14 + Supabase + Stripe SaaS"),
        ("portfolio-site", "~/projects/portfolio-site", "Astro + TailwindCSS portfolio"),
        ("api-backend", "~/projects/api-backend", "FastAPI + PostgreSQL REST API"),
        ("mobile-app", "~/projects/mobile-app", "React Native + Expo mobile app"),
        ("discord-bot", "~/projects/discord-bot", "Discord.js bot with slash commands"),
    ]
    for name, path, dna in projects:
        db.execute("INSERT INTO projects VALUES (?, ?, ?, ?)",
                   (name, path, dna, (now - timedelta(hours=random.randint(1, 48))).isoformat()))

    # --- Facts ---
    demo_facts = _generate_comprehensive_facts() if comprehensive else _generate_basic_facts()

    fact_ids = []
    for i, (proj, content, ftype, domain, heat, tier) in enumerate(demo_facts):
        fid = str(uuid.uuid4())
        fact_ids.append((fid, proj))
        age_hours = int((1.0 - heat) * 200) + random.randint(0, 48)
        ts = (now - timedelta(hours=age_hours)).isoformat()
        retrieval = int(heat * 15) + random.randint(0, 5)
        tags = f"{domain},{ftype}" if random.random() > 0.5 else domain
        db.execute(
            "INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fid, proj, content, ftype, domain, tags, f"src/{domain}/{ftype}.py",
             None, None, ts, heat, retrieval, tier, None)
        )

    # --- Sessions ---
    outcomes = ["productive", "debugging", "planning", "exploratory", "maintenance"]
    session_titles = [
        ("my-saas-app", "Bug fix: auth, billing", "debugging"),
        ("my-saas-app", "Decision: architecture", "planning"),
        ("my-saas-app", "Knowledge: api, deploy", "productive"),
        ("my-saas-app", "Session: ui, storage", "productive"),
        ("my-saas-app", "Procedure: auth", "productive"),
        ("portfolio-site", "Pattern: architecture, ui", "productive"),
        ("portfolio-site", "Knowledge: email, deploy", "exploratory"),
        ("portfolio-site", "Performance: ui", "maintenance"),
        ("api-backend", "Bug fix: database", "debugging"),
        ("api-backend", "Knowledge: auth, infrastructure", "productive"),
        ("api-backend", "Pattern: api, architecture", "productive"),
        ("api-backend", "Task: testing", "maintenance"),
        ("mobile-app", "Pattern: navigation, storage", "productive"),
        ("mobile-app", "Gotcha discovery: testing", "debugging"),
        ("mobile-app", "Knowledge: notifications", "exploratory"),
        ("discord-bot", "Bug fix: commands", "debugging"),
        ("discord-bot", "Knowledge: architecture, database", "productive"),
    ]

    for i, (proj, title, outcome) in enumerate(session_titles):
        sid = str(uuid.uuid4())
        start = now - timedelta(hours=(len(session_titles) - i) * 8 + random.randint(0, 4))
        end = start + timedelta(minutes=random.randint(15, 120))
        facts_c = random.randint(1, 8)
        changes_c = random.randint(2, 25)
        bridge = f"Progress: {title}. Changes: {changes_c} files modified. Open: continue with next feature."
        db.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, proj, start.isoformat(), end.isoformat(), None, bridge,
             title, proj, outcome, facts_c, changes_c)
        )

    # --- Knowledge Gaps ---
    gaps = [
        ("my-saas-app", "how to handle subscription cancellation", 0, 0.12, 4),
        ("my-saas-app", "email template customization", 0, 0.08, 2),
        ("api-backend", "websocket authentication pattern", 0, 0.15, 3),
        ("api-backend", "database backup procedure", 0, 0.05, 5),
        ("mobile-app", "deep linking configuration", 0, 0.21, 2),
        ("discord-bot", "slash command permissions", 1, 0.67, 1),
    ]
    for proj, query, resolved, score, times in gaps:
        first = (now - timedelta(days=random.randint(1, 14))).isoformat()
        last = (now - timedelta(hours=random.randint(1, 48))).isoformat()
        db.execute(
            "INSERT INTO knowledge_gaps (project, query, hit_count, best_score, first_seen, last_seen, times_seen, resolved) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (proj, query, 0, score, first, last, times, resolved)
        )

    # --- Contradictions ---
    if len(fact_ids) > 10:
        db.execute(
            "INSERT INTO contradictions (project, fact_id_a, fact_id_b, reason, detected, resolved) VALUES (?, ?, ?, ?, ?, ?)",
            ("my-saas-app", fact_ids[0][0], fact_ids[11][0],
             "Conflicting deployment targets: Vercel vs self-hosted mentioned",
             (now - timedelta(hours=12)).isoformat(), 0)
        )
        db.execute(
            "INSERT INTO contradictions (project, fact_id_a, fact_id_b, reason, detected, resolved) VALUES (?, ?, ?, ?, ?, ?)",
            ("api-backend", fact_ids[17][0], fact_ids[23][0],
             "Auth requirement conflict: JWT required vs public endpoints list mismatch",
             (now - timedelta(hours=6)).isoformat(), 0)
        )

    # --- Clusters ---
    cluster_data = [
        ("my-saas-app", "Authentication & Security", "Supabase auth, RLS, JWT, middleware", 4),
        ("my-saas-app", "Billing & Payments", "Stripe integration, pricing, webhooks", 3),
        ("my-saas-app", "Deployment & DevOps", "Vercel, CI/CD, database migrations", 3),
        ("api-backend", "Database Layer", "PostgreSQL, Alembic, query optimization", 4),
        ("api-backend", "API Design", "Pydantic, pagination, rate limiting", 3),
        ("mobile-app", "App Architecture", "Navigation, offline storage, notifications", 3),
    ]
    cluster_id = 1
    for proj, label, summary, count in cluster_data:
        db.execute(
            "INSERT INTO fact_clusters (id, project, label, summary, fact_count, created) VALUES (?, ?, ?, ?, ?, ?)",
            (cluster_id, proj, label, summary, count, (now - timedelta(hours=24)).isoformat())
        )
        # Assign some facts to clusters
        proj_facts = [f for f in fact_ids if f[1] == proj]
        for fid, _ in proj_facts[:count]:
            db.execute("UPDATE facts SET cluster_id = ? WHERE id = ?", (cluster_id, fid))
        cluster_id += 1

    # --- Changes (file change log) ---
    files = [
        "src/app/page.tsx", "src/app/api/auth/route.ts", "src/lib/stripe.ts",
        "src/components/Dashboard.tsx", "src/middleware.ts", "package.json",
        "src/app/api/webhooks/stripe/route.ts", "tailwind.config.ts",
    ]
    for i in range(45):
        proj = random.choice([p[0] for p in projects])
        db.execute(
            "INSERT INTO changes (project, file_path, action, timestamp) VALUES (?, ?, ?, ?)",
            (proj, random.choice(files), random.choice(["Write", "Edit"]),
             (now - timedelta(hours=random.randint(0, 96))).isoformat())
        )

    # --- Code Intelligence tables ---
    db.executescript("""
        CREATE TABLE IF NOT EXISTS code_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            file_path TEXT NOT NULL,
            language TEXT NOT NULL,
            file_mtime REAL NOT NULL,
            file_size INTEGER DEFAULT 0,
            symbol_count INTEGER DEFAULT 0,
            is_dirty INTEGER DEFAULT 0,
            indexed_at TEXT NOT NULL,
            UNIQUE(project, file_path)
        );
        CREATE TABLE IF NOT EXISTS code_symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            file_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            parent_id INTEGER,
            signature TEXT,
            docstring TEXT,
            exported INTEGER DEFAULT 0,
            FOREIGN KEY (file_id) REFERENCES code_files(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS code_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            file_id INTEGER NOT NULL,
            from_symbol_id INTEGER,
            to_symbol_id INTEGER,
            to_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            line INTEGER NOT NULL,
            confidence REAL DEFAULT 0.5,
            FOREIGN KEY (file_id) REFERENCES code_files(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_code_symbols_kind ON code_symbols(project, kind);
    """)

    indexed_at = now.isoformat()

    # --- Demo code files (TypeScript SaaS + Python API) ---
    demo_files = [
        ("my-saas-app", "src/app/page.tsx", "typescript", 1024, 3),
        ("my-saas-app", "src/lib/auth.ts", "typescript", 2048, 4),
        ("my-saas-app", "src/lib/stripe.ts", "typescript", 1536, 3),
        ("my-saas-app", "src/components/Dashboard.tsx", "typescript", 3072, 4),
        ("api-backend", "app/main.py", "python", 890, 2),
        ("api-backend", "app/routers/users.py", "python", 1420, 3),
        ("api-backend", "app/models/user.py", "python", 960, 2),
    ]

    file_id_map = {}
    for proj, fpath, lang, size, sym_count in demo_files:
        db.execute(
            "INSERT INTO code_files (project, file_path, language, file_mtime, file_size, symbol_count, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (proj, fpath, lang, 1709500000.0, size, sym_count, indexed_at)
        )
        fid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        file_id_map[fpath] = fid

    # --- Demo symbols (18 symbols) ---
    demo_symbols = [
        # src/app/page.tsx
        ("my-saas-app", "src/app/page.tsx", "HomePage", "HomePage", "function", 1, 45, None, "(): JSX.Element", "Main landing page component", 1),
        ("my-saas-app", "src/app/page.tsx", "HeroSection", "HeroSection", "function", 47, 82, None, "(): JSX.Element", "Hero section with CTA", 0),
        ("my-saas-app", "src/app/page.tsx", "PricingCard", "PricingCard", "function", 84, 120, None, "(props: PricingProps): JSX.Element", "Pricing tier card component", 1),
        # src/lib/auth.ts
        ("my-saas-app", "src/lib/auth.ts", "AuthProvider", "AuthProvider", "class", 1, 85, None, None, "Authentication context provider", 1),
        ("my-saas-app", "src/lib/auth.ts", "signIn", "AuthProvider.signIn", "method", 20, 42, None, "(email: string, password: string): Promise<User>", "Sign in with email/password", 0),
        ("my-saas-app", "src/lib/auth.ts", "signOut", "AuthProvider.signOut", "method", 44, 58, None, "(): Promise<void>", "Sign out current user", 0),
        ("my-saas-app", "src/lib/auth.ts", "UserRole", "UserRole", "enum", 87, 92, None, None, "User role enumeration", 1),
        # src/lib/stripe.ts
        ("my-saas-app", "src/lib/stripe.ts", "createCheckout", "createCheckout", "function", 5, 35, None, "(priceId: string, userId: string): Promise<Session>", "Create Stripe checkout session", 1),
        ("my-saas-app", "src/lib/stripe.ts", "handleWebhook", "handleWebhook", "function", 37, 80, None, "(event: Stripe.Event): Promise<void>", "Process Stripe webhook events", 1),
        ("my-saas-app", "src/lib/stripe.ts", "SubscriptionStatus", "SubscriptionStatus", "type_alias", 82, 82, None, "type SubscriptionStatus = 'active' | 'canceled' | 'past_due'", None, 1),
        # src/components/Dashboard.tsx
        ("my-saas-app", "src/components/Dashboard.tsx", "Dashboard", "Dashboard", "function", 1, 95, None, "(): JSX.Element", "Main dashboard component", 1),
        ("my-saas-app", "src/components/Dashboard.tsx", "StatsPanel", "StatsPanel", "function", 97, 130, None, "(props: StatsPanelProps): JSX.Element", None, 0),
        ("my-saas-app", "src/components/Dashboard.tsx", "DashboardProps", "DashboardProps", "interface", 132, 140, None, None, "Props for Dashboard component", 1),
        ("my-saas-app", "src/components/Dashboard.tsx", "useDashboardData", "useDashboardData", "function", 142, 165, None, "(): DashboardData", "Custom hook for dashboard data fetching", 0),
        # app/main.py
        ("api-backend", "app/main.py", "create_app", "create_app", "function", 1, 25, None, "() -> FastAPI", "Factory function for FastAPI application", 1),
        ("api-backend", "app/main.py", "health_check", "health_check", "function", 27, 32, None, "() -> dict", "Health check endpoint", 1),
        # app/routers/users.py
        ("api-backend", "app/routers/users.py", "get_users", "get_users", "function", 10, 28, None, "(db: Session, skip: int = 0, limit: int = 20) -> list[User]", "List users with pagination", 1),
        ("api-backend", "app/routers/users.py", "get_user", "get_user", "function", 30, 42, None, "(user_id: int, db: Session) -> User", "Get single user by ID", 1),
        ("api-backend", "app/routers/users.py", "UserCreate", "UserCreate", "class", 44, 52, None, None, "Pydantic model for user creation", 1),
        # app/models/user.py
        ("api-backend", "app/models/user.py", "User", "User", "class", 1, 25, None, None, "SQLAlchemy User model", 1),
        ("api-backend", "app/models/user.py", "UserRole", "UserRole", "enum", 27, 32, None, None, "User role enumeration for backend", 1),
    ]

    symbol_id_map = {}
    for proj, fpath, name, qname, kind, ls, le, parent, sig, doc, exported in demo_symbols:
        fid = file_id_map[fpath]
        db.execute(
            "INSERT INTO code_symbols (project, file_id, name, qualified_name, kind, line_start, line_end, parent_id, signature, docstring, exported) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (proj, fid, name, qname, kind, ls, le, parent, sig, doc, exported)
        )
        sid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        symbol_id_map[qname] = sid

    # Set parent_id for methods
    for qname in ["AuthProvider.signIn", "AuthProvider.signOut"]:
        if qname in symbol_id_map and "AuthProvider" in symbol_id_map:
            db.execute("UPDATE code_symbols SET parent_id = ? WHERE id = ?",
                       (symbol_id_map["AuthProvider"], symbol_id_map[qname]))

    # --- Demo references (10 references) ---
    demo_refs = [
        # Dashboard calls auth and stripe
        ("my-saas-app", "src/components/Dashboard.tsx", "Dashboard", "AuthProvider", "call", 15, 0.9),
        ("my-saas-app", "src/components/Dashboard.tsx", "Dashboard", "useDashboardData", "call", 8, 0.95),
        ("my-saas-app", "src/components/Dashboard.tsx", "StatsPanel", "DashboardProps", "type_ref", 98, 0.8),
        # HomePage uses components
        ("my-saas-app", "src/app/page.tsx", "HomePage", "Dashboard", "call", 20, 0.9),
        ("my-saas-app", "src/app/page.tsx", "HomePage", "PricingCard", "call", 30, 0.95),
        ("my-saas-app", "src/app/page.tsx", "PricingCard", "createCheckout", "call", 95, 0.85),
        # Auth imports
        ("my-saas-app", "src/lib/auth.ts", "AuthProvider.signIn", "UserRole", "type_ref", 25, 0.8),
        # Python backend
        ("api-backend", "app/routers/users.py", "get_users", "User", "type_ref", 12, 0.9),
        ("api-backend", "app/routers/users.py", "get_user", "User", "type_ref", 33, 0.9),
        ("api-backend", "app/main.py", "create_app", "get_users", "import", 5, 0.85),
    ]

    for proj, fpath, from_qname, to_qname, kind, line, confidence in demo_refs:
        fid = file_id_map.get(fpath, 1)
        from_id = symbol_id_map.get(from_qname)
        to_id = symbol_id_map.get(to_qname)
        db.execute(
            "INSERT INTO code_references (project, file_id, from_symbol_id, to_symbol_id, to_name, kind, line, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (proj, fid, from_id, to_id, to_qname, kind, line, confidence)
        )

    db.commit()
    db.close()
    return db_path


def _generate_basic_facts() -> list[tuple]:
    """Generate basic demo facts (for minimal demo)."""
    return [
        # my-saas-app
        ("my-saas-app", "Auth uses Supabase with row-level security (RLS) enabled on all tables", "fact", "auth", 0.92, "active"),
        ("my-saas-app", "Stripe webhook endpoint is /api/webhooks/stripe — must verify signature", "api_contract", "billing", 0.85, "active"),
        ("my-saas-app", "NEVER use getServerSideProps — all pages use App Router server components", "gotcha", "architecture", 0.95, "active"),
        ("my-saas-app", "Database migrations run via Supabase CLI: supabase db push", "command", "deploy", 0.78, "active"),
        ("my-saas-app", "Pricing page uses static data from /lib/pricing.ts — not from DB", "decision", "billing", 0.71, "active"),
        ("my-saas-app", "User onboarding flow: signup → verify email → select plan → dashboard", "procedure", "auth", 0.65, "reference"),
        ("my-saas-app", "Rate limiting on API: 100 req/min per user, implemented in middleware.ts", "pattern", "api", 0.58, "reference"),
        ("my-saas-app", "CSS uses Tailwind with custom design tokens in tailwind.config.ts", "fact", "ui", 0.42, "reference"),
        ("my-saas-app", "Image uploads go to Supabase Storage bucket 'avatars' with 5MB limit", "api_contract", "storage", 0.35, "reference"),
        ("my-saas-app", "Fixed: CORS error on /api/webhooks — needed to exclude from middleware auth check", "error_fix", "api", 0.28, "archive"),
        ("my-saas-app", "React Query cache time set to 5 minutes for dashboard data", "performance", "api", 0.22, "archive"),
        ("my-saas-app", "Deployment: Vercel with preview deploys on PR, production on main", "fact", "deploy", 0.15, "archive"),

        # portfolio-site
        ("portfolio-site", "Uses Astro content collections for blog posts in /src/content/blog/", "pattern", "architecture", 0.88, "active"),
        ("portfolio-site", "Contact form sends via Resend API — key in RESEND_API_KEY env var", "api_contract", "email", 0.75, "active"),
        ("portfolio-site", "Dark mode toggle uses prefers-color-scheme + localStorage fallback", "pattern", "ui", 0.62, "reference"),
        ("portfolio-site", "Images optimized with Astro Image component — WebP format, lazy loading", "performance", "ui", 0.45, "reference"),
        ("portfolio-site", "Deploy to Netlify via git push to main branch", "command", "deploy", 0.31, "archive"),

        # api-backend
        ("api-backend", "All endpoints require JWT auth except /health and /auth/login", "api_contract", "auth", 0.91, "active"),
        ("api-backend", "Database uses Alembic for migrations: alembic upgrade head", "command", "database", 0.82, "active"),
        ("api-backend", "Pydantic v2 models for request/response validation in /app/schemas/", "pattern", "architecture", 0.73, "active"),
        ("api-backend", "Background tasks use Celery with Redis broker on port 6379", "dependency", "infrastructure", 0.68, "active"),
        ("api-backend", "Fixed: N+1 query in /users endpoint — added joinedload for user.roles", "error_fix", "database", 0.55, "reference"),
        ("api-backend", "Pagination pattern: offset/limit with max 100 items, default 20", "pattern", "api", 0.41, "reference"),
        ("api-backend", "Docker compose: app (8000), postgres (5432), redis (6379), worker", "fact", "infrastructure", 0.33, "archive"),
        ("api-backend", "Test coverage at 84% — missing coverage in webhook handlers", "task", "testing", 0.19, "archive"),

        # mobile-app
        ("mobile-app", "Navigation uses React Navigation v6 with typed routes in /navigation/types.ts", "pattern", "navigation", 0.87, "active"),
        ("mobile-app", "Push notifications via Expo Push API — token stored in user profile", "api_contract", "notifications", 0.76, "active"),
        ("mobile-app", "Offline mode: AsyncStorage caches last 50 items, syncs on reconnect", "pattern", "storage", 0.64, "reference"),
        ("mobile-app", "GOTCHA: iOS simulator doesn't support push notifications — use TestFlight", "gotcha", "testing", 0.52, "reference"),
        ("mobile-app", "App store deployment: eas build + eas submit", "command", "deploy", 0.38, "archive"),

        # discord-bot
        ("discord-bot", "Commands registered via REST API on bot startup — not guild-specific", "fact", "architecture", 0.83, "active"),
        ("discord-bot", "Rate limit: 50 messages per channel per 10 seconds", "performance", "api", 0.69, "active"),
        ("discord-bot", "SQLite database for user XP/levels stored in /data/bot.db", "dependency", "database", 0.47, "reference"),
        ("discord-bot", "Fixed: Bot crashes on DM — added guild check before accessing member roles", "error_fix", "commands", 0.34, "archive"),
    ]


def _generate_comprehensive_facts() -> list[tuple]:
    """Generate comprehensive demo facts (50+ facts across multiple projects)."""
    facts = _generate_basic_facts()

    # Add more facts for my-saas-app
    saas_facts = [
        ("my-saas-app", "Environment variables validated using Zod schema in /lib/env.ts", "pattern", "config", 0.89, "active"),
        ("my-saas-app", "Team feature: max 5 members on Starter plan, unlimited on Pro", "api_contract", "billing", 0.84, "active"),
        ("my-saas-app", "Password reset tokens expire after 1 hour", "api_contract", "auth", 0.81, "active"),
        ("my-saas-app", "API rate limits reset every minute at :00 seconds", "pattern", "api", 0.77, "active"),
        ("my-saas-app", "Webhooks retried up to 3 times with exponential backoff", "pattern", "integrations", 0.74, "active"),
        ("my-saas-app", "Database connection pool: max 20 connections", "performance", "database", 0.72, "active"),
        ("my-saas-app", "Session cookies use 'lax' SameSite policy", "decision", "security", 0.70, "active"),
        ("my-saas-app", "File uploads validated by MIME type and magic bytes", "pattern", "security", 0.68, "reference"),
        ("my-saas-app", "Invoice PDFs generated using Puppeteer", "dependency", "billing", 0.66, "reference"),
        ("my-saas-app", "Redis used for session storage and rate limiting counters", "dependency", "infrastructure", 0.63, "reference"),
        ("my-saas-app", "Email templates stored in /templates/emails/ using Handlebars", "pattern", "email", 0.61, "reference"),
        ("my-saas-app", "Health check endpoint at /api/health returns 200 OK", "api_contract", "deploy", 0.59, "reference"),
        ("my-saas-app", "Sentry configured for error tracking in production only", "dependency", "monitoring", 0.56, "reference"),
        ("my-saas-app", "Fixed: Memory leak in dashboard component — unsubscribed from event listener", "error_fix", "performance", 0.48, "archive"),
        ("my-saas-app", "Previous auth implementation used Auth0, migrated to Supabase", "decision", "auth", 0.25, "archive"),
        ("my-saas-app", "Old deployment used AWS Amplify, migrated to Vercel for edge functions", "decision", "deploy", 0.20, "archive"),
    ]

    # Add more facts for api-backend
    api_facts = [
        ("api-backend", "SQLAlchemy 2.0 style queries with select() and session.execute()", "pattern", "database", 0.86, "active"),
        ("api-backend", "JWT tokens valid for 24 hours, refresh tokens for 7 days", "api_contract", "auth", 0.83, "active"),
        ("api-backend", "Request validation uses FastAPI dependency injection", "pattern", "api", 0.79, "active"),
        ("api-backend", "Database transactions managed via context managers", "pattern", "database", 0.76, "active"),
        ("api-backend", "Logging structured as JSON for log aggregation", "pattern", "monitoring", 0.71, "reference"),
        ("api-backend", "CORS configured to allow localhost:3000 in development", "config", "security", 0.67, "reference"),
        ("api-backend", "pytest fixtures in conftest.py for database setup/teardown", "pattern", "testing", 0.64, "reference"),
        ("api-backend", "Makefile targets: test, lint, format, migrate", "command", "devops", 0.62, "reference"),
        ("api-backend", "Pre-commit hooks for black, ruff, and mypy", "pattern", "devops", 0.57, "reference"),
        ("api-backend", "Fixed: Race condition in user registration — added unique constraint", "error_fix", "database", 0.44, "archive"),
        ("api-backend", "Previously used Flask, migrated to FastAPI for auto-generated docs", "decision", "architecture", 0.30, "archive"),
    ]

    # Add more facts for mobile-app
    mobile_facts = [
        ("mobile-app", "Biometric auth uses Expo LocalAuthentication API", "api_contract", "auth", 0.85, "active"),
        ("mobile-app", "State management with Zustand for global store", "pattern", "architecture", 0.80, "active"),
        ("mobile-app", "API client auto-refreshes JWT tokens on 401 responses", "pattern", "api", 0.75, "active"),
        ("mobile-app", "Image picker configured for max 5 photos at once", "api_contract", "ui", 0.69, "reference"),
        ("mobile-app", "Deep links use custom URL scheme: myapp://", "api_contract", "navigation", 0.65, "reference"),
        ("mobile-app", "Background location tracking requires 'always' permission", "gotcha", "permissions", 0.53, "reference"),
        ("mobile-app", "OTA updates via Expo Updates, checks on app launch", "pattern", "deploy", 0.46, "archive"),
        ("mobile-app", "Fixed: Keyboard avoiding view issue on iPhone SE", "error_fix", "ui", 0.40, "archive"),
    ]

    # Add more facts for portfolio-site
    portfolio_facts = [
        ("portfolio-site", "RSS feed auto-generated at /rss.xml", "feature", "seo", 0.78, "active"),
        ("portfolio-site", "Sitemap includes all blog posts and project pages", "pattern", "seo", 0.73, "active"),
        ("portfolio-site", "View transitions API for page navigation", "pattern", "ui", 0.66, "reference"),
        ("portfolio-site", "Analytics using Plausible (privacy-friendly)", "dependency", "monitoring", 0.54, "reference"),
        ("portfolio-site", "Fixed: Mobile menu not closing on route change", "error_fix", "ui", 0.43, "archive"),
    ]

    # Add more facts for discord-bot
    bot_facts = [
        ("discord-bot", "Command cooldowns: 5 seconds per user per command", "pattern", "performance", 0.82, "active"),
        ("discord-bot", "Leveling system: XP gained per message with anti-spam", "feature", "gamification", 0.71, "active"),
        ("discord-bot", "Moderation logs sent to #mod-logs channel", "api_contract", "moderation", 0.68, "reference"),
        ("discord-bot", "Music playback uses Lavalink node", "dependency", "features", 0.49, "reference"),
        ("discord-bot", "Custom prefix configurable per guild (!default)", "feature", "config", 0.45, "reference"),
        ("discord-bot", "Fixed: Memory leak in music queue — cleared on disconnect", "error_fix", "performance", 0.36, "archive"),
    ]

    facts.extend(saas_facts)
    facts.extend(api_facts)
    facts.extend(mobile_facts)
    facts.extend(portfolio_facts)
    facts.extend(bot_facts)

    return facts
