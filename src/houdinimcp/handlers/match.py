"""The one name pattern that every tool reads."""
import fnmatch


def matches(pattern, *texts):
    """True when any of `texts` matches `pattern`.

    `|` separates alternatives, for example "time|step|cfl". Each one is a glob
    ("*retarget*") or a part of the text, with no case. No pattern matches all.
    """
    if not pattern:
        return True
    texts = [text.lower() for text in texts if text]
    return any(one and any(fnmatch.fnmatch(text, one) or one in text for text in texts)
               for one in (part.strip() for part in pattern.lower().split("|")))
