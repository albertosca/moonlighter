"""MetricsHighlighter gives the op= summary line's keys and values, outcome words and job ids their own styles, and styles a status word only when it stands alone."""

from moonlighter.core.log import MetricsHighlighter
from rich.text import Text


def test_metrics_highlighter_colors_op_summary_line():
    """op= observability lines (core/metrics.py) must stand out from ordinary
    log text — key=value pairs get their own styles instead of falling through
    ReprHighlighter's generic 'no style' default.
    """
    highlighter = MetricsHighlighter()
    text = Text("op=scan_and_evaluate calls=1 total_seconds=0.523 spend_limit_hits=0")
    highlighter.highlight(text)

    styled = {text.plain[span.start : span.end]: span.style for span in text.spans}
    assert styled.get("op=scan_and_evaluate") == "repr.op_name"
    assert styled.get("calls") == "repr.metric_key"
    assert styled.get("1") == "repr.metric_value"


def test_metrics_highlighter_colors_status_words_and_job_id():
    """Scanning a log line for outcome (filled/failed/skipped) and which job
    it's about (#2646) currently requires reading plain white text word by
    word — these get their own color so severity/outcome pop at a glance.
    """
    highlighter = MetricsHighlighter()
    text = Text("Job #2646: fill_form 3 filled, 1 failed:not_visible, 1 skipped")
    highlighter.highlight(text)

    styled = {text.plain[span.start : span.end]: span.style for span in text.spans}
    assert styled.get("#2646") == "repr.job_id"
    assert styled.get("filled") == "repr.status_ok"
    assert styled.get("failed:not_visible") == "repr.status_fail"
    assert styled.get("skipped") == "repr.status_attn"


def test_metrics_highlighter_status_words_need_word_boundary():
    """'fulfilled' must not light up as status_ok just because it contains
    the substring 'filled' — only the whole word counts as a status.
    """
    highlighter = MetricsHighlighter()
    text = Text("the request was fulfilled")
    highlighter.highlight(text)

    styled = {text.plain[span.start : span.end]: span.style for span in text.spans}
    assert "filled" not in styled
    assert "fulfilled" not in styled
