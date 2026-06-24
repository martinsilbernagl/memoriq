"""Tests for secrets filtering in memory_write."""


def test_block_openai_api_key(temp_db, active_session):
    """Should block OpenAI API keys."""
    from tools.memory_write import memory_write
    result = memory_write(content="API key is sk-proj-abc123def456ghi789jkl012mno345")
    assert "blocked" in result.lower() or "blokovano" in result.lower()


def test_block_anthropic_api_key(temp_db, active_session):
    """Should block Anthropic API keys."""
    from tools.memory_write import memory_write
    result = memory_write(content="Key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz")
    assert "blocked" in result.lower() or "blokovano" in result.lower()


def test_block_github_token(temp_db, active_session):
    """Should block GitHub personal access tokens."""
    from tools.memory_write import memory_write
    result = memory_write(content="Use token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij")
    assert "blocked" in result.lower() or "blokovano" in result.lower()


def test_block_aws_key(temp_db, active_session):
    """Should block AWS access keys."""
    from tools.memory_write import memory_write
    result = memory_write(content="AWS key: AKIAIOSFODNN7EXAMPLE")
    assert "blocked" in result.lower() or "blokovano" in result.lower()


def test_block_private_key(temp_db, active_session):
    """Should block private keys."""
    from tools.memory_write import memory_write
    result = memory_write(content="-----BEGIN RSA PRIVATE KEY-----\nMIIE...")
    assert "blocked" in result.lower() or "blokovano" in result.lower()


def test_block_password_in_config(temp_db, active_session):
    """Should block password= patterns."""
    from tools.memory_write import memory_write
    result = memory_write(content="Database config: password=SuperSecret123!")
    assert "blocked" in result.lower() or "blokovano" in result.lower()


def test_block_connection_string(temp_db, active_session):
    """Should block database connection strings with credentials."""
    from tools.memory_write import memory_write
    result = memory_write(content="DB: postgres://admin:secret@localhost:5432/mydb")
    assert "blocked" in result.lower() or "blokovano" in result.lower()


def test_block_bearer_token(temp_db, active_session):
    """Should block Bearer tokens."""
    from tools.memory_write import memory_write
    result = memory_write(content="Auth header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123")
    assert "blocked" in result.lower() or "blokovano" in result.lower()


def test_block_slack_token(temp_db, active_session):
    """Should block Slack tokens."""
    from tools.memory_write import memory_write
    result = memory_write(content="Slack bot: xoxb-123456789012-1234567890123-AbCdEfGhIjKl")
    assert "blocked" in result.lower() or "blokovano" in result.lower()


def test_allow_normal_content(temp_db, active_session):
    """Normal content should NOT be blocked."""
    from tools.memory_write import memory_write
    result = memory_write(content="Use PostgreSQL with Supabase for auth. Deploy on Vercel.")
    assert "blocked" not in result.lower() and "blokovano" not in result.lower()


def test_allow_code_patterns(temp_db, active_session):
    """Code-like content without actual secrets should pass."""
    from tools.memory_write import memory_write
    result = memory_write(content="The API endpoint is /api/auth/login, uses JWT tokens for session management")
    assert "blocked" not in result.lower() and "blokovano" not in result.lower()


def test_allow_secret_discussion(temp_db, active_session):
    """Discussing secrets conceptually should pass."""
    from tools.memory_write import memory_write
    result = memory_write(content="Store API keys in .env file, never commit to git")
    assert "blocked" not in result.lower() and "blokovano" not in result.lower()
