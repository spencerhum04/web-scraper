from config.loader import KeywordConfig
from scrapers.matching import KeywordMatcher, normalize_text
from scrapers.types import JobCandidate


def test_normalize_text_folds_punctuation_and_spacing():
    assert normalize_text(" AI/ML   Co-op ") == "ai ml co op"


def test_matcher_accepts_title_with_both_keyword_groups():
    matcher = KeywordMatcher(
        KeywordConfig(
            role_keywords=("software", "developer"),
            internship_keywords=("intern", "internship"),
        )
    )

    result = matcher.match_candidate(
        JobCandidate(
            title_text="Software Engineering Intern",
            context_text="",
            url="https://example.com/jobs/1",
        )
    )

    assert result is not None
    assert result.used_context is False


def test_matcher_uses_same_card_context_as_fallback():
    matcher = KeywordMatcher(
        KeywordConfig(
            role_keywords=("developer",),
            internship_keywords=("intern",),
        )
    )

    result = matcher.match_candidate(
        JobCandidate(
            title_text="Developer",
            context_text="Toronto | Winter 2026 Intern",
            url="https://example.com/jobs/2",
        )
    )

    # After the new rule, the internship keyword in context should not
    # be sufficient; the title must contain both keyword groups.
    assert result is None


def test_matcher_rejects_non_intern_role():
    matcher = KeywordMatcher(
        KeywordConfig(
            role_keywords=("software",),
            internship_keywords=("intern",),
        )
    )

    result = matcher.match_candidate(
        JobCandidate(
            title_text="Software Engineer",
            context_text="Full-time role",
            url="https://example.com/jobs/3",
        )
    )

    assert result is None


def test_matcher_keeps_broad_config_keywords_authoritative():
    matcher = KeywordMatcher(
        KeywordConfig(
            role_keywords=("data", "ai"),
            internship_keywords=("intern",),
        )
    )

    result = matcher.match_candidate(
        JobCandidate(
            title_text="Data Engineer Intern",
            context_text="",
            url="https://example.com/jobs/4",
        )
    )

    assert result is not None
    assert "data" in result.matched_role_keywords
