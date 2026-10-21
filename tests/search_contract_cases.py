"""Literal, independently specified search examples shared with the real server.

Every body is distinct; queries must match exactly their own fixture record.
"""
LITERAL_SEARCH_CASES = (
    ('a*b', 'prefix a*b suffix'),
    ('a%b', 'prefix a%b suffix'),
    ('a_b', 'prefix a_b suffix'),
    (r'a\b', r'prefix a\b suffix'),
    ('a.b', 'prefix a.b suffix'),
    ('a[b]', 'prefix a[b] suffix'),
    ('a(b)', 'prefix a(b) suffix'),
    ('a|b', 'prefix a|b suffix'),
    ('a+b', 'prefix a+b suffix'),
    ('a?b', 'prefix a?b suffix'),
    ('a{2}b', 'prefix a{2}b suffix'),
    ('a^b', 'prefix a^b suffix'),
    ('a$b', 'prefix a$b suffix'),
    ('a"b', 'prefix a"b suffix'),
    ('a,b', 'prefix a,b suffix'),
    ("O'Reilly", "prefix O'Reilly suffix"),
    ('繁中 (小課)', 'prefix 繁中 (小課) suffix'),
    ('CaSeMiXeD', 'prefix casemixed suffix'),
)
