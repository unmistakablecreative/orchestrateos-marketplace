#!/usr/bin/env python3
"""
Programmatic slop pattern detector.
Run on text BEFORE editing to identify violations.

Usage:
    python3 detect_slop.py "your text here"
    python3 detect_slop.py --file input.txt

Returns JSON with violations by category and line numbers.
"""

import re
import sys
import json
import argparse
from collections import Counter


# Common verbs for fragment detection
COMMON_VERBS = {
    'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'done',
    'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can',
    'get', 'got', 'gets', 'make', 'makes', 'made', 'take', 'takes', 'took',
    'go', 'goes', 'went', 'come', 'comes', 'came', 'see', 'sees', 'saw',
    'know', 'knows', 'knew', 'think', 'thinks', 'thought',
    'want', 'wants', 'wanted', 'need', 'needs', 'needed',
    'find', 'finds', 'found', 'give', 'gives', 'gave',
    'tell', 'tells', 'told', 'feel', 'feels', 'felt',
    'try', 'tries', 'tried', 'leave', 'leaves', 'left',
    'call', 'calls', 'called', 'keep', 'keeps', 'kept',
    'let', 'lets', 'put', 'puts', 'show', 'shows', 'showed',
    'run', 'runs', 'ran', 'move', 'moves', 'moved',
    'live', 'lives', 'lived', 'believe', 'believes', 'believed',
    'create', 'creates', 'created', 'build', 'builds', 'built',
    'fail', 'fails', 'failed', 'work', 'works', 'worked',
    'generate', 'generates', 'generated', 'consume', 'consumes', 'consumed',
    'cost', 'costs', 'spend', 'spends', 'spent', 'pay', 'pays', 'paid',
    "didn't", "doesn't", "don't", "won't", "can't", "couldn't", "shouldn't",
    "isn't", "aren't", "wasn't", "weren't", "haven't", "hasn't", "hadn't"
}

# Throat-clearing phrases to detect
THROAT_CLEARERS = [
    r"here'?s the thing:?",
    r"let me be clear:?",
    r"in other words,?",
    r"to put it simply,?",
    r"the reality is,?",
    r"the truth is,?",
    r"it'?s important to note that",
    r"it goes without saying",
    r"needless to say",
    r"at the end of the day",
    r"it'?s worth noting that",
    r"interestingly,?",
    r"arguably,?",
    r"one might say",
    r"it could be argued that",
]

# Article self-reference patterns
SELF_REFERENCES = [
    r"in this article",
    r"this article will",
    r"as discussed earlier",
    r"by the end of this article",
    r"as mentioned above",
    r"as we discussed",
    r"as you can see",
    r"as i said earlier",
    r"let'?s now turn to",
    r"having established .+, we can now",
    r"with that in mind,?",
]

# Banned AI words
BANNED_WORDS = [
    'delve', 'tapestry', 'vibrant', 'landscape', 'multifaceted',
    'nuanced', 'intricate', 'pivotal', 'paramount', 'foster',
    'comprehensive', 'robust', 'leverage', 'utilize', 'facilitate',
    'endeavor', 'embark', 'realm', 'beacon', 'cornerstone',
    'synergy', 'align', 'optimize', 'streamline', 'scalable',
    'ecosystem', 'paradigm', 'holistic', 'innovative', 'cutting-edge',
    'best-in-class', 'world-class', 'state-of-the-art',
    'actionable', 'impactful', 'transformative'
]


def split_sentences(text):
    """Split text into sentences with line tracking."""
    lines = text.split('\n')
    sentences = []

    for line_num, line in enumerate(lines, 1):
        # Skip empty lines and markdown headers
        if not line.strip() or line.strip().startswith('#'):
            continue
        # Split on sentence endings
        parts = re.split(r'(?<=[.!?])\s+', line.strip())
        for part in parts:
            if part.strip():
                sentences.append({'text': part.strip(), 'line': line_num})

    return sentences


def detect_anaphora(sentences):
    """Detect 3+ consecutive sentences starting with same word."""
    violations = []
    if len(sentences) < 3:
        return violations

    i = 0
    while i < len(sentences) - 2:
        first_words = []
        for j in range(i, min(i + 10, len(sentences))):
            words = sentences[j]['text'].split()
            if words:
                first_words.append((words[0].lower().strip('.,!?:'), sentences[j]['line']))

        # Check for 3+ consecutive same first words
        count = 1
        for k in range(1, len(first_words)):
            if first_words[k][0] == first_words[k-1][0]:
                count += 1
                if count >= 3:
                    lines = [first_words[m][1] for m in range(k-count+1, k+1)]
                    violations.append({
                        'pattern': 'anaphora',
                        'word': first_words[k][0],
                        'count': count,
                        'lines': list(set(lines)),
                        'message': f'"{first_words[k][0]}" starts {count} consecutive sentences'
                    })
            else:
                count = 1
        i += 1

    # Deduplicate
    seen = set()
    unique = []
    for v in violations:
        key = (v['word'], tuple(sorted(v['lines'])))
        if key not in seen:
            seen.add(key)
            unique.append(v)

    return unique


def detect_triple_repetition(text):
    """Detect 'no X, no Y, no Z' patterns."""
    violations = []
    lines = text.split('\n')

    pattern = r'\b(no|not|never|without|cannot|can\'t|won\'t|couldn\'t)\s+\w+[\s,]+\1\s+\w+[\s,]+\1\s+\w+'

    for line_num, line in enumerate(lines, 1):
        matches = re.findall(pattern, line, re.IGNORECASE)
        if matches:
            violations.append({
                'pattern': 'triple_repetition',
                'line': line_num,
                'text': line.strip()[:100],
                'message': 'Triple repetition pattern detected'
            })

    return violations


def detect_fragments(sentences):
    """Detect sentences without verbs (likely fragments)."""
    violations = []

    for s in sentences:
        text = s['text'].lower()
        words = text.split()

        # Skip very short or very long sentences
        if len(words) < 3 or len(words) > 8:
            continue

        # Check if any word is a verb
        has_verb = any(word.strip('.,!?:;') in COMMON_VERBS for word in words)

        if not has_verb:
            violations.append({
                'pattern': 'fragment',
                'line': s['line'],
                'text': s['text'][:80],
                'message': 'Possible fragment (no verb detected)'
            })

    return violations


def detect_two_word_sentences(sentences):
    """Detect sentences with 2 or fewer words."""
    violations = []

    for s in sentences:
        words = s['text'].split()
        if 1 <= len(words) <= 2:
            violations.append({
                'pattern': 'two_word_sentence',
                'line': s['line'],
                'text': s['text'],
                'message': 'Very short sentence (false emphasis)'
            })

    return violations


def detect_orphan_references(text):
    """Detect stats/numbers mentioned only once."""
    violations = []

    # Find all numbers with context
    pattern = r'(\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|thousand|B|M|K))?|\d+(?:\.\d+)?%|\d+(?:,\d+)+)'
    matches = re.findall(pattern, text)

    counts = Counter(matches)
    orphans = [num for num, count in counts.items() if count == 1]

    if orphans:
        lines = text.split('\n')
        for orphan in orphans:
            for line_num, line in enumerate(lines, 1):
                if orphan in line:
                    violations.append({
                        'pattern': 'orphan_reference',
                        'line': line_num,
                        'value': orphan,
                        'message': f'Statistic "{orphan}" appears only once - integrate or remove'
                    })
                    break

    return violations


def detect_throat_clearing(text):
    """Detect throat-clearing opener phrases."""
    violations = []
    lines = text.split('\n')

    for line_num, line in enumerate(lines, 1):
        for phrase in THROAT_CLEARERS:
            if re.search(phrase, line, re.IGNORECASE):
                violations.append({
                    'pattern': 'throat_clearing',
                    'line': line_num,
                    'text': line.strip()[:80],
                    'message': 'Throat-clearing opener - delete it'
                })
                break

    return violations


def detect_self_references(text):
    """Detect article self-references."""
    violations = []
    lines = text.split('\n')

    for line_num, line in enumerate(lines, 1):
        for phrase in SELF_REFERENCES:
            if re.search(phrase, line, re.IGNORECASE):
                violations.append({
                    'pattern': 'self_reference',
                    'line': line_num,
                    'text': line.strip()[:80],
                    'message': 'Article self-reference - delete it'
                })
                break

    return violations


def detect_banned_words(text):
    """Detect banned AI fingerprint words."""
    violations = []
    lines = text.split('\n')

    for line_num, line in enumerate(lines, 1):
        for word in BANNED_WORDS:
            if re.search(r'\b' + word + r'\b', line, re.IGNORECASE):
                violations.append({
                    'pattern': 'banned_word',
                    'line': line_num,
                    'word': word,
                    'message': f'Banned AI word: "{word}"'
                })

    return violations


def detect_em_dash_overload(text):
    """Detect paragraphs with multiple em-dashes."""
    violations = []
    paragraphs = text.split('\n\n')

    line_offset = 1
    for para in paragraphs:
        dash_count = para.count('—') + para.count('--')
        if dash_count > 2:
            violations.append({
                'pattern': 'em_dash_overload',
                'line': line_offset,
                'count': dash_count,
                'message': f'{dash_count} em-dashes in one paragraph - simplify'
            })
        line_offset += para.count('\n') + 2

    return violations


def detect_colon_abuse(text):
    """Detect multiple colons in quick succession."""
    violations = []
    lines = text.split('\n')

    colon_lines = []
    for line_num, line in enumerate(lines, 1):
        if ':' in line and not line.strip().startswith('#'):
            colon_lines.append(line_num)

    # Check for 3+ colons in 5 consecutive lines
    for i in range(len(colon_lines) - 2):
        if colon_lines[i+2] - colon_lines[i] <= 5:
            violations.append({
                'pattern': 'colon_abuse',
                'lines': colon_lines[i:i+3],
                'message': '3+ colons in quick succession'
            })

    return violations


def detect_slop(text):
    """Run all detection patterns on text."""
    sentences = split_sentences(text)

    results = {
        'anaphora': detect_anaphora(sentences),
        'triple_repetition': detect_triple_repetition(text),
        'fragments': detect_fragments(sentences),
        'two_word_sentences': detect_two_word_sentences(sentences),
        'orphan_references': detect_orphan_references(text),
        'throat_clearing': detect_throat_clearing(text),
        'self_references': detect_self_references(text),
        'banned_words': detect_banned_words(text),
        'em_dash_overload': detect_em_dash_overload(text),
        'colon_abuse': detect_colon_abuse(text),
    }

    # Summary
    total = sum(len(v) for v in results.values())
    results['summary'] = {
        'total_violations': total,
        'by_category': {k: len(v) for k, v in results.items() if k != 'summary'}
    }

    return results


def main():
    parser = argparse.ArgumentParser(description='Detect slop patterns in text')
    parser.add_argument('text', nargs='?', help='Text to analyze')
    parser.add_argument('--file', '-f', help='Read text from file')
    args = parser.parse_args()

    if args.file:
        with open(args.file, 'r') as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        # Read from stdin
        text = sys.stdin.read()

    results = detect_slop(text)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
