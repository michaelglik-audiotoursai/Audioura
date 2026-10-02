#!/usr/bin/env python3
"""
Translation Service - AudioTours Multi-Language Support
Port: 5030
"""

from flask import Flask, request, jsonify, make_response
import boto3
import zipfile
import io
import re
import uuid
import time
import threading
import psycopg2
import logging
import requests
from concurrent.futures import ThreadPoolExecutor
import os
import json
from bs4 import BeautifulSoup, NavigableString

# [LOCAL-559] Centralised cost rates (gpt-4o-mini input/output per 1M tokens).
try:
    import cost_rates
except ImportError:  # pragma: no cover - cost_rates lives at repo root; present in the image
    cost_rates = None

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


class TranslationArtifactError(Exception):
    """Raised when a translation cannot produce a valid downloadable artifact.

    The caller MUST treat this as a hard failure: no translation row is inserted,
    and the HTTP endpoint returns a non-200 response with error code
    TRANSLATION_ARTIFACT_FAILED. This prevents the historic bug (GCS-TR1) where an
    artifact-less row was inserted and then 404'd from map-delivery/download-tour.
    """
    error_code = "TRANSLATION_ARTIFACT_FAILED"


class TranslationService:
    # [LOCAL-559] Chunk boundary: texts longer than this are split on blank lines
    # (paragraph boundaries) and translated piecewise, then rejoined in order.
    # Applies to BOTH engines so neither silently truncates (the old AWS path sent
    # Text=text[:5000] and dropped everything past 5,000 characters).
    _CHUNK_THRESHOLD_CHARS = 4500
    # AWS Translate hard limit is 10,000 bytes per request; keep a safe ceiling.
    _AWS_MAX_CHARS = 9000

    # [LOCAL-559] LLM engine defaults.
    _LLM_MODEL = os.getenv('TRANSLATION_LLM_MODEL', 'gpt-4o-mini')
    _LLM_ENDPOINT = 'https://api.openai.com/v1/chat/completions'
    _LLM_TIMEOUT = int(os.getenv('TRANSLATION_LLM_TIMEOUT', '60'))
    # Sane bounds for the LLM output length ratio (translated_len / source_len).
    # Outside this range the output is almost certainly wrong (truncated, refused,
    # or hallucinated) and we fall back to AWS for that call.
    _LLM_RATIO_MIN = 0.5
    _LLM_RATIO_MAX = 2.5

    # Human-readable language names for the LLM system prompt.
    _LANGUAGE_NAMES = {
        'es': 'Spanish', 'fr': 'French', 'de': 'German', 'ru': 'Russian',
        'zh': 'Chinese', 'ko': 'Korean', 'ja': 'Japanese', 'it': 'Italian',
        'pt': 'Portuguese', 'ar': 'Arabic', 'hi': 'Hindi', 'nl': 'Dutch',
        'pl': 'Polish', 'tr': 'Turkish', 'uk': 'Ukrainian', 'he': 'Hebrew',
    }

    # [LOCAL-559] Voice-command phrases that must remain English in article text so the
    # mobile voice controls keep matching. Shared by the LLM prompt and the AWS post-pass.
    _VOICE_COMMANDS = [
        "Play", "Pause", "Next topic", "Previous topic", "Repeat",
        "Forward 10 seconds", "Backward 5 seconds", "Play topic",
        "Play summary", "Play full article", "List major topics",
        "Next article", "Previous article", "What are my options"
    ]

    def __init__(self):
        self.translate_client = boto3.client('translate', region_name='us-east-1')
        self.polly_client = boto3.client('polly', region_name='us-east-1')
        self.executor = ThreadPoolExecutor(max_workers=5)
        # [LOCAL-559] Translation engine selector. Default 'aws' keeps today's
        # behaviour so nothing deployed changes until TRANSLATION_ENGINE=llm is set.
        self.translation_engine = os.getenv('TRANSLATION_ENGINE', 'aws').strip().lower()
        if self.translation_engine not in ('aws', 'llm'):
            logging.warning(
                f"[TRANSLATE] Unknown TRANSLATION_ENGINE={self.translation_engine!r}; defaulting to 'aws'"
            )
            self.translation_engine = 'aws'
        self._openai_api_key = os.getenv('OPENAI_API_KEY', '')
        # [LOCAL-559] In-process memo of identical (text, language) pairs. The HTML/ZIP
        # paths translate the same fragments (names, labels, repeated stops) repeatedly;
        # memoising avoids paying for them twice within a process.
        self._translation_memo = {}
        self._memo_lock = threading.Lock()
        # [LOCAL-559] Per-process LLM cost accumulator and a per-tour counter the tour
        # path resets at the start of each translation to report a per-tour total.
        self._llm_cost_total = 0.0
        self._llm_tour_cost = 0.0
        # [LOCAL-559R] Stops are now translated concurrently (bounded pool), so the
        # cost accumulators are mutated from worker threads — guard them with a lock.
        self._cost_lock = threading.Lock()

    def get_db_connection(self):
        return psycopg2.connect(
            host=os.getenv('DB_HOST', 'development-postgres-2-1'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
    
    # Only these two labels must stay in English — mobile app parses them by exact string match.
    # All other labels (Type/Specialty, Orientation, etc.) should be translated normally.
    _METADATA_LABELS = ['Coordinates', 'Address']

    # Compiled pattern for stripping translated metadata label lines from .txt body.
    # Matches any line whose first word(s) correspond to a _METADATA_LABELS key followed
    # by any non-word separator (covers ASCII ':', full-width '\uff1a', French '\xa0:', etc.)
    _TRANSLATED_LABEL_RE = re.compile(
        r'^\s*\S+\W.*$',  # placeholder — built dynamically per-label in _restore_metadata_labels
        re.IGNORECASE
    )

    def _restore_metadata_labels(self, original_text, translated_text, target_language):
        """Insert original English Coordinates/Address lines after the title line of the translated stop.
        Mobile app parses these fields by exact English string match to place map pins.
        [LOCAL-5] Previously prepended at the very top, which caused the metadata to be jammed
        onto the 'Stop N:' line during reassembly (the title ended up on line 3 instead of line 1).
        Now inserts AFTER the first non-empty line (the title), preserving correct structure:
            <title>
            Address: ...
            Coordinates: ...
            <rest of translated body>
        The translated label lines (e.g. Coordonnees\xa0:) are stripped from the body so the
        .txt file does not contain duplicate coordinate entries."""
        if target_language == 'en':
            return translated_text
        english_lines = []
        for label in self._METADATA_LABELS:
            m = re.search(
                rf'^({re.escape(label)}\s*:.*)$',
                original_text, re.IGNORECASE | re.MULTILINE
            )
            if m:
                english_lines.append(m.group(1).strip())
        if not english_lines:
            return translated_text
        # Strip translated equivalents from body to avoid duplicate entries.
        # [LOCAL-5] Previous word-count heuristic was fragile for languages that attach colons
        # directly to words (Russian: "Адрес:" vs French: "Coordonnées :"). New approach:
        # 1. For Coordinates: match any line containing the exact coordinate pair from the
        #    English original (numbers don't change in translation).
        # 2. For Address: match any line with a colon that contains the address value text
        #    (street number + partial address content from the English line).
        # 3. Fall back to the old heuristic for edge cases.
        body_lines = translated_text.split('\n')
        
        # Extract the raw values from the English metadata lines for matching
        _coord_pattern = None
        _addr_value = None
        for eline in english_lines:
            if eline.lower().startswith('coordinates'):
                # Extract the coordinate pair for matching in translated text
                cm = re.search(r'([-\d.]+\s*,\s*[-\d.]+)', eline)
                if cm:
                    _coord_pattern = cm.group(1).replace(' ', '')  # normalize spaces
            elif eline.lower().startswith('address'):
                # Extract the address value (after "Address: ")
                _addr_value = re.sub(r'^Address\s*:\s*', '', eline, flags=re.IGNORECASE).strip()
        
        def _is_translated_metadata(line):
            stripped = line.strip()
            if not stripped:
                return False
            # Don't strip lines that ARE the English metadata labels we prepended
            if any(re.match(rf'^{re.escape(lbl)}\s*:', stripped, re.IGNORECASE)
                   for lbl in self._METADATA_LABELS):
                return False
            # Match translated coordinates line: any line containing the exact coordinate pair
            if _coord_pattern:
                line_no_spaces = stripped.replace(' ', '').replace('\xa0', '')
                if _coord_pattern.replace(' ', '') in line_no_spaces:
                    # Confirm it looks like a label line (has a colon before the numbers)
                    if ':' in stripped.split(_coord_pattern.split(',')[0])[0]:
                        return True
            # Match translated address line: contains key address fragments
            if _addr_value:
                # Check if the line contains significant address fragments (street number, postal code)
                addr_numbers = re.findall(r'\d+', _addr_value)
                if addr_numbers and len(addr_numbers) >= 2:
                    # Line contains at least 2 of the same numbers as the original address
                    line_numbers = re.findall(r'\d+', stripped)
                    matches = sum(1 for n in addr_numbers if n in line_numbers)
                    if matches >= 2 and ':' in stripped[:30]:
                        return True
            return False
        clean_body = [l for l in body_lines if not _is_translated_metadata(l)]
        # [LOCAL-5] Insert English metadata lines AFTER the title (first non-empty line),
        # not at the top. This preserves the structure: Stop N: <title>\n<metadata>\n<body>
        title_line = None
        rest_lines = []
        for i, line in enumerate(clean_body):
            if line.strip():
                title_line = line
                rest_lines = clean_body[i+1:]
                break
        if title_line is not None:
            return '\n'.join([title_line] + [''] + english_lines + [''] + rest_lines)
        else:
            # No title found — fall back to prepending (shouldn't happen in normal operation)
            return '\n'.join(english_lines + clean_body)

    def translate_text(self, text, target_language, preserve_voice_commands=False):
        """Translate text, dispatching on the TRANSLATION_ENGINE flag.

        [LOCAL-559]
          * engine 'aws'  (DEFAULT): AWS Translate — today's behaviour.
          * engine 'llm'          : OpenAI gpt-4o-mini, with AWS fallback per call.

        Neither engine truncates: input over ~4,500 chars is split on blank lines
        (paragraph boundaries), each chunk translated, and the pieces rejoined in
        order. This fixes the live defect where the AWS path sent Text=text[:5000]
        and silently dropped everything past 5,000 characters.

        Results are memoised per (text, language, engine) within the process, so the
        HTML/ZIP paths do not pay to translate the same fragment twice.
        """
        if target_language == 'en' or text is None or text == '':
            return text

        engine = self.translation_engine
        memo_key = (engine, target_language, bool(preserve_voice_commands), text)
        with self._memo_lock:
            if memo_key in self._translation_memo:
                return self._translation_memo[memo_key]

        translated = self._translate_dispatch(text, target_language, preserve_voice_commands, engine)

        with self._memo_lock:
            self._translation_memo[memo_key] = translated
        return translated

    def _translate_dispatch(self, text, target_language, preserve_voice_commands, engine):
        """Chunk if needed, then run the selected engine on each chunk."""
        chunks = self._split_for_translation(text)
        if len(chunks) > 1:
            logging.info(
                f"[TRANSLATE] Split {len(text)} chars into {len(chunks)} chunk(s) "
                f"(engine={engine}, lang={target_language}) — no truncation"
            )
        out_parts = []
        for chunk in chunks:
            if engine == 'llm':
                out_parts.append(self._translate_text_llm(chunk, target_language, preserve_voice_commands))
            else:
                out_parts.append(self._translate_text_aws(chunk, target_language, preserve_voice_commands))
        # Chunks were split on the blank line between paragraphs; rejoin with the
        # same separator so the paragraph structure (and line count) is preserved.
        return '\n\n'.join(out_parts)

    def _split_for_translation(self, text):
        """Split text into translate-sized chunks on blank lines (paragraph breaks).

        [LOCAL-559] Returns a list of chunks each <= _CHUNK_THRESHOLD_CHARS where
        possible. Short texts return as a single-element list (no behavioural change).
        A single paragraph longer than the threshold is kept whole here (so we never
        break a line mid-way and change the line count); the AWS engine additionally
        guards the 10k-byte hard limit by line-splitting such giants.
        """
        if len(text) <= self._CHUNK_THRESHOLD_CHARS:
            return [text]
        paragraphs = text.split('\n\n')
        chunks = []
        current = []
        current_len = 0
        for para in paragraphs:
            para_len = len(para) + 2  # account for the '\n\n' separator
            if current and current_len + para_len > self._CHUNK_THRESHOLD_CHARS:
                chunks.append('\n\n'.join(current))
                current = [para]
                current_len = para_len
            else:
                current.append(para)
                current_len += para_len
        if current:
            chunks.append('\n\n'.join(current))
        return chunks

    def _translate_text_aws(self, text, target_language, preserve_voice_commands=False):
        """AWS Translate for a single chunk. No truncation: a chunk still larger than
        the AWS per-request limit is split further on single newlines and rejoined."""
        try:
            if len(text) > self._AWS_MAX_CHARS:
                # Preserve every character: split on single newlines, translate, rejoin.
                lines = text.split('\n')
                buf, buf_len, pieces = [], 0, []
                for ln in lines:
                    if buf and buf_len + len(ln) + 1 > self._AWS_MAX_CHARS:
                        pieces.append('\n'.join(buf))
                        buf, buf_len = [ln], len(ln) + 1
                    else:
                        buf.append(ln)
                        buf_len += len(ln) + 1
                if buf:
                    pieces.append('\n'.join(buf))
                translated_text = '\n'.join(
                    self._aws_translate_call(p, target_language) for p in pieces
                )
            else:
                translated_text = self._aws_translate_call(text, target_language)

            if preserve_voice_commands:
                translated_text = self._preserve_voice_commands(text, translated_text, target_language)
            return translated_text
        except Exception as e:
            logging.error(f"Translation error: {e}")
            return text

    def _aws_translate_call(self, text, target_language):
        """Single AWS Translate API call (no [:5000] truncation)."""
        response = self.translate_client.translate_text(
            Text=text,
            SourceLanguageCode='en',
            TargetLanguageCode=target_language
        )
        return response['TranslatedText']

    def _translate_text_llm(self, text, target_language, preserve_voice_commands=False):
        """Translate a single chunk with gpt-4o-mini, falling back to AWS on failure.

        [LOCAL-559] Fallback to AWS for THIS call (logged as [TRANSLATE-LLM] FALLBACK)
        when the LLM errors, returns empty, or returns a line count / length ratio
        outside sane bounds. Cost is metered per call and accumulated per tour.
        """
        lang_name = self._LANGUAGE_NAMES.get(target_language, target_language)
        # [LOCAL-559R] The old prompt said "keep lines starting with
        # Address:/Coordinates:/Type-Specialty:/Specific Examples:/Operational Details:
        # UNCHANGED". gpt-4o-mini generalised that to EVERY 'Label:' line and left the
        # SPOKEN 'Orientation:' and 'Directions:' lines in English — a Russian listener
        # heard English directions. The fix: translate EVERYTHING, including the
        # 'Orientation:' and 'Directions:' labels and their text, and only special-case
        # the five nav lines below (and only Address:/Coordinates: keep their value too).
        system_prompt = (
            f"You are a professional translator. Translate the user's text faithfully into {lang_name}. "
            "Preserve the exact meaning with no additions and no omissions. "
            "Keep every line break and the SAME NUMBER OF LINES as the input. "
            "Translate EVERY line, INCLUDING lines that begin with a label such as "
            "'Orientation:' or 'Directions:' — you MUST translate the label WORD itself "
            "(e.g. 'Directions:' and 'Orientation:') into the target language as well as "
            "the text after it. Never leave the English words 'Directions' or "
            "'Orientation' in the output. "
            "There are exactly FIVE special lines, identified ONLY by these exact English "
            "label prefixes: 'Address:', 'Coordinates:', 'Type/Specialty:', "
            "'Specific Examples:' and 'Operational Details:'. For these five lines, keep the "
            "label word itself in English and translate only the text after the colon — "
            "EXCEPT 'Address:' and 'Coordinates:', whose values are postal/numeric data and "
            "must be left exactly as written. Do NOT treat any other 'Label:' line as special. "
            "Keep names of venues and people as they are commonly written in that language. "
            "Output only the translation, with no commentary, labels, or quotes."
        )
        if preserve_voice_commands:
            # [LOCAL-559] Voice-command preservation under the LLM engine: instruct the
            # model to leave these control phrases in English so the article voice
            # controls keep working. A post-pass (_preserve_voice_commands) is still run
            # as a backstop for any the model translated anyway.
            _cmds = ', '.join(f'"{c}"' for c in self._VOICE_COMMANDS)
            system_prompt += (
                " Keep the following voice-command phrases in English exactly as written, "
                f"do not translate them: {_cmds}."
            )

        # [LOCAL-559R] One LLM attempt, then — if the output contains lines that came
        # back UNTRANSLATED (byte-identical, not one of the five nav lines, with real
        # words in them) — ONE retry with the same prompt, then AWS fallback. All other
        # failure modes (error / empty / line-count / ratio) fall back to AWS immediately.
        reason = None
        for attempt in range(2):  # attempt 0 = first call, attempt 1 = single retry
            try:
                if not self._openai_api_key:
                    reason = 'no_api_key'
                    raise RuntimeError('OPENAI_API_KEY not set')

                resp = self._openai_chat(system_prompt, text)
                translated = (resp.get('text') or '').strip('\n')
                # [LOCAL-559R] Deterministically repair spoken labels: when the model
                # translated a Directions:/Orientation: VALUE but kept the English label,
                # swap just the label word for its translation. This fixes the common
                # case without a retry/fallback (which is slow), while a line that is
                # STILL fully English falls through to the untranslated check below.
                translated = self._normalize_spoken_labels(text, translated, target_language)
                reason = self._evaluate_llm_output(text, translated)

                if reason is None:
                    # Meter cost only for an accepted LLM result.
                    self._meter_llm_cost(resp.get('input_tokens', 0), resp.get('output_tokens', 0))
                    if preserve_voice_commands:
                        translated = self._preserve_voice_commands(text, translated, target_language)
                    return translated
            except Exception as e:
                reason = f'error {e}'

            # Only an untranslated-lines failure is worth a retry — the model saw a
            # valid prompt and simply left some lines in English. Any other reason
            # (error/empty/line_count/ratio) will not improve on a blind retry.
            is_untranslated = reason is not None and reason.startswith('untranslated_lines=')
            if is_untranslated and attempt == 0:
                logging.warning(f"[TRANSLATE-LLM] RETRY {reason}")
                continue
            break

        logging.warning(f"[TRANSLATE-LLM] FALLBACK {reason}")
        return self._translate_text_aws(text, target_language, preserve_voice_commands)

    def _evaluate_llm_output(self, source_text, translated):
        """Validate one LLM translation. Return a failure reason string, or None if OK.

        [LOCAL-559R] Checks, in order: empty, line-count drift, length ratio, and the
        new DETERMINISTIC untranslated-line check (byte-identical non-nav lines with
        real words). The untranslated reason is reported as 'untranslated_lines=N' so
        the caller can retry once before falling back to AWS.
        """
        if not translated.strip():
            return 'empty'
        src_lines = source_text.count('\n') + 1
        out_lines = translated.count('\n') + 1
        if out_lines != src_lines:
            return f'line_count {out_lines}!={src_lines}'
        ratio = len(translated) / max(len(source_text), 1)
        if ratio < self._LLM_RATIO_MIN or ratio > self._LLM_RATIO_MAX:
            return f'ratio {ratio:.2f}'
        n_untranslated = self._count_untranslated_lines(source_text, translated)
        if n_untranslated > 0:
            return f'untranslated_lines={n_untranslated}'
        return None

    # [LOCAL-559R] A line is "untranslated" when it is byte-identical to its source
    # line, is NOT one of the five nav lines, and carries real words (>=4 words of
    # 4+ letters). Short/numeric/punctuation-only lines and proper-noun-only lines
    # are legitimately identical across languages and must not trip the check.
    _WORD_RE = re.compile(r'[^\W\d_]{4,}', re.UNICODE)  # a "letters-word" of length >= 4

    # [LOCAL-559R] Spoken label lines that MUST be fully translated (label + value).
    # These are NOT among the five nav lines, so they must never keep their English
    # label. gpt-4o-mini frequently translates the VALUE but leaves the English label
    # (e.g. 'Directions: Dirígete hacia el sur ...' in Spanish) — which the mobile app
    # speaks aloud, so a listener hears the English word 'Directions'. Any output line
    # that still starts with one of these English labels is treated as untranslated.
    _SPOKEN_LABELS = ('Orientation:', 'Directions:')

    def _is_nav_line(self, stripped_line):
        """True if the line is one of the five nav lines (by exact English label prefix)."""
        return any(
            re.match(rf'^{re.escape(prefix)}', stripped_line, re.IGNORECASE)
            for prefix in self._NAV_FIELD_PREFIXES
        )

    def _keeps_english_spoken_label(self, stripped_src, stripped_out):
        """True if the SOURCE line was a spoken label line and the OUTPUT still begins
        with the English label (so the label was not translated)."""
        if not any(stripped_src.startswith(lbl) for lbl in self._SPOKEN_LABELS):
            return False
        return any(stripped_out.startswith(lbl) for lbl in self._SPOKEN_LABELS)

    def _count_untranslated_lines(self, source_text, translated_text):
        """Count output lines that look untranslated per the LOCAL-559R definition.

        Only meaningful when line counts match (the caller guarantees this before
        calling). A line counts as untranslated iff EITHER:
          (a) it is byte-identical to the aligned source line, is not one of the five
              nav lines, and contains 4 or more words of 4+ letters (prose, not a
              name/number/short label the model is right to leave alone); OR
          (b) the source line was a spoken label line ('Orientation:'/'Directions:')
              and the output still begins with that English label — the value may be
              translated but the SPOKEN label is not, and the app reads it aloud.
        """
        src_lines = source_text.split('\n')
        tr_lines = translated_text.split('\n')
        if len(src_lines) != len(tr_lines):
            return 0  # not comparable positionally; handled by the line_count check
        n = 0
        for src, tr in zip(src_lines, tr_lines):
            src_s, tr_s = src.strip(), tr.strip()
            # (b) spoken label left in English (even if the value was translated)
            if self._keeps_english_spoken_label(src_s, tr_s):
                n += 1
                continue
            if src != tr:
                continue  # changed → translated
            # (a) fully byte-identical prose line
            if not src_s or self._is_nav_line(src_s):
                continue
            if len(self._WORD_RE.findall(src_s)) >= 4:
                n += 1
        return n

    def _translate_spoken_label(self, label_word, target_language):
        """Translate a bare spoken-label word (e.g. 'Directions') via AWS Translate,
        memoised per (word, language). AWS is used (not the LLM) because it is cheap,
        deterministic, and the labels are exactly what the AWS engine already produces
        (e.g. 'Cómo llegar', 'Как добраться'). Returns the English word on any failure
        so we never crash the main path."""
        memo_key = ('__label__', target_language, label_word)
        with self._memo_lock:
            if memo_key in self._translation_memo:
                return self._translation_memo[memo_key]
        try:
            translated = self._aws_translate_call(label_word, target_language).strip()
            if not translated:
                translated = label_word
        except Exception as e:
            logging.warning(f"[TRANSLATE-LLM] label translate failed for {label_word!r}: {e}")
            translated = label_word
        with self._memo_lock:
            self._translation_memo[memo_key] = translated
        return translated

    def _normalize_spoken_labels(self, source_text, translated_text, target_language):
        """Repair spoken-label lines whose VALUE was translated but whose LABEL stayed
        English. For each aligned (source, output) line where the source begins with a
        spoken label ('Orientation:'/'Directions:'), the output still begins with that
        English label, AND the output value differs from the English value (i.e. the
        value WAS translated), replace the English label word with its translation.
        Lines that are still fully English are left untouched so the untranslated check
        can flag them for retry/fallback."""
        src_lines = source_text.split('\n')
        tr_lines = translated_text.split('\n')
        if len(src_lines) != len(tr_lines):
            return translated_text
        changed = False
        for idx, (src, tr) in enumerate(zip(src_lines, tr_lines)):
            src_s = src.strip()
            for label in self._SPOKEN_LABELS:          # 'Orientation:' / 'Directions:'
                if not src_s.startswith(label):
                    continue
                tr_s = tr.strip()
                if not tr_s.startswith(label):
                    break  # label already translated — nothing to do
                src_val = src_s[len(label):].strip()
                tr_val = tr_s[len(label):].strip()
                if tr_val and tr_val != src_val:
                    # Value translated, label English → swap only the label word.
                    word = label[:-1]  # drop trailing ':'
                    new_label = self._translate_spoken_label(word, target_language)
                    tr_lines[idx] = f"{new_label}: {tr_val}"
                    changed = True
                break
        return '\n'.join(tr_lines) if changed else translated_text

    def _openai_chat(self, system_prompt, user_text):
        """Call the OpenAI chat completions endpoint (gpt-4o-mini, temperature 0).

        Returns a dict: {text, input_tokens, output_tokens}. Isolated in its own
        method so unit tests can mock the network call cleanly.
        """
        response = requests.post(
            self._LLM_ENDPOINT,
            headers={
                'Authorization': f'Bearer {self._openai_api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': self._LLM_MODEL,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_text},
                ],
                'temperature': 0,
            },
            timeout=self._LLM_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(f'OpenAI HTTP {response.status_code}: {response.text[:200]}')
        data = response.json()
        usage = data.get('usage', {}) or {}
        return {
            'text': data['choices'][0]['message']['content'],
            'input_tokens': usage.get('prompt_tokens', 0),
            'output_tokens': usage.get('completion_tokens', 0),
        }

    def _meter_llm_cost(self, input_tokens, output_tokens):
        """Log and accumulate the cost of one accepted LLM translation call."""
        if cost_rates is not None:
            cost = cost_rates.llm_cost(
                input_tokens=input_tokens, output_tokens=output_tokens, model=self._LLM_MODEL
            )
        else:  # pragma: no cover - defensive; cost_rates ships in the image
            cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
        with self._cost_lock:
            self._llm_cost_total += cost
            self._llm_tour_cost += cost
        logging.info(
            f"[TRANSLATE-LLM] tokens_in={input_tokens} tokens_out={output_tokens} cost=${cost:.6f}"
        )
        return cost

    def _preserve_voice_commands(self, original_text, translated_text, target_language='ru'):
        """Preserve English voice commands in translated text"""
        # Voice commands that must stay in English
        voice_commands = self._VOICE_COMMANDS
        
        # Preserve voice command phrases
        for command in voice_commands:
            if command in original_text:
                # Find translated version and replace back to English
                try:
                    translated_command = self.translate_client.translate_text(
                        Text=command,
                        SourceLanguageCode='en',
                        TargetLanguageCode=target_language
                    )['TranslatedText']
                    translated_text = translated_text.replace(translated_command, command)
                except:
                    pass  # Keep original if translation fails
        
        return translated_text
    
    def generate_audio(self, text, target_language):
        """Generate audio using AWS Polly"""
        voice_map = {
            'en': 'Joanna',
            'es': 'Lucia',
            'fr': 'Celine', 
            'de': 'Marlene',
            'ru': 'Tatyana',
            'zh': 'Zhiyu',
            'ko': 'Seoyeon'
        }
        
        try:
            response = self.polly_client.synthesize_speech(
                Text=text[:3000],  # AWS limit
                OutputFormat='mp3',
                VoiceId=voice_map.get(target_language, 'Joanna')
            )
            return response['AudioStream'].read()
        except Exception as e:
            logging.error(f"Audio generation error: {e}")
            return None

    def _translate_one_stop(self, i, stop_text, n_stops, target_language):
        """Translate a single stop and derive its TTS text. Returns (translated_stop, tts_text).

        [LOCAL-559R] Extracted from the former serial loop so stops can be translated
        concurrently (bounded pool). The per-stop logic is unchanged: translate the raw
        stop, strip nav fields positionally for TTS (two-pass fallback on line drift),
        then restore the English Coordinates/Address labels. On any error the English
        text is kept for both outputs, exactly as before.
        """
        try:
            raw_translated = self.translate_text(stop_text, target_language)

            # [LOCAL-142] Try single-pass: strip nav fields positionally from
            # the raw translation (before _restore_metadata_labels modifies it).
            tts_text = self._strip_nav_fields_from_translated(stop_text, raw_translated)
            if tts_text is None:
                # Fallback: line counts diverged — use two-pass (costs one extra API call)
                logging.warning(
                    f"[LOCAL-142] Positional strip fallback on stop {i+1}/{n_stops} "
                    f"(en_lines={len(stop_text.split(chr(10)))}, "
                    f"tr_lines={len(raw_translated.split(chr(10)))})"
                )
                tts_text = self.translate_text(
                    self._strip_nav_fields_for_tts(stop_text), target_language
                )

            translated_stop = self._restore_metadata_labels(
                stop_text, raw_translated, target_language
            )
            logging.info(f"Translated stop {i+1}/{n_stops}")
            return translated_stop, tts_text
        except Exception as e:
            logging.error(f"Error translating stop {i+1}: {e}")
            return stop_text, stop_text  # Keep original on error

    def translate_tour_with_audio(self, original_tour_id, target_language):
        """Translate a tour with full audio generation preserving original HTML structure.
        
        Returns:
            tuple: (translated_tour_id or None, cache_hit: bool)
                   cache_hit=True when a translation already existed and was returned as-is.
        """
        # [LOCAL-559] Reset the per-tour LLM cost accumulator so we can report a
        # per-tour total at the end (engine='aws' leaves this at 0.0).
        self._llm_tour_cost = 0.0
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Get original tour with tour_content
            cursor.execute(
                "SELECT id, tour_name, request_string, audio_tour, number_requested, lat, lng, tour_content, content_language, tour_blob_uri, stops_count FROM audio_tours WHERE id = %s", 
                (original_tour_id,)
            )
            original_tour = cursor.fetchone()
            if not original_tour:
                logging.error(f"Original tour {original_tour_id} not found")
                return None, False
            
            tour_content = original_tour[7]  # tour_content column
            original_zip_data = original_tour[3]  # audio_tour column
            tour_blob_uri = original_tour[9] if len(original_tour) > 9 else None  # R2 blob key

            # GCS-TR1 fix: fetch the source ZIP from R2 whenever audio_tour is NULL and
            # tour_blob_uri is set — REGARDLESS of tour_content. The R2 migration set the
            # audio_tour BYTEA column to NULL for migrated tours, so R2-migrated tours that
            # still have tour_content (e.g. 107/120/284) previously skipped this fetch and
            # crashed later in _create_mobile_compatible_zip with original_zip_data == None.
            if not original_zip_data and tour_blob_uri:
                logging.info(f"Tour {original_tour_id}: audio_tour is NULL, fetching source ZIP from R2 blob: {tour_blob_uri}")
                try:
                    from blobstorage import R2BlobStorage
                    original_zip_data = R2BlobStorage().download(tour_blob_uri)
                    logging.info(f"Downloaded {len(original_zip_data)} bytes from R2 for tour {original_tour_id}")
                except Exception as r2_err:
                    # Do not proceed to INSERT an artifact-less row. Signal a hard failure so
                    # the endpoint returns non-200 and the caller can retry/report.
                    logging.error(f"Failed to download source ZIP for tour {original_tour_id} from R2 ({tour_blob_uri}): {r2_err}")
                    raise TranslationArtifactError(
                        f"source ZIP unobtainable for tour {original_tour_id} (blob {tour_blob_uri}): {r2_err}"
                    )

            if not tour_content:
                logging.warning(f"No tour content found for tour {original_tour_id}, falling back to ZIP extraction")

                # Source ZIP is required for the fallback path.
                if not original_zip_data:
                    logging.error(f"Tour {original_tour_id} has no tour_content AND no ZIP data — cannot translate")
                    # [GCS-TR1] Hard-fail: never insert an artifact-less row.
                    raise TranslationArtifactError(
                        f"tour {original_tour_id} has no tour_content and no source ZIP"
                    )
                try:
                    import io as _io
                    zip_bytes = original_zip_data.tobytes() if hasattr(original_zip_data, 'tobytes') else bytes(original_zip_data)
                    with zipfile.ZipFile(_io.BytesIO(zip_bytes)) as _z:
                        audio_files_in_zip = [n for n in _z.namelist() if n.startswith('audio_') and n.endswith('.mp3')]
                    if not audio_files_in_zip:
                        logging.error(f"Tour {original_tour_id} ZIP has no audio files and no tour_content — cannot translate")
                        # [GCS-TR1] Hard-fail: never insert an artifact-less row.
                        raise TranslationArtifactError(
                            f"tour {original_tour_id} ZIP has no audio files and no tour_content"
                        )
                except zipfile.BadZipFile:
                    pass
                # [LOCAL-60] Preserve the (id, cache_hit) tuple contract. The ZIP path is
                # always a fresh translation, so cache_hit is False.
                _zip_result = self._translate_tour_from_zip(original_tour, target_language, zip_data_override=original_zip_data)
                return _zip_result, False


            logging.info(f"Using stored tour content: {len(tour_content)} characters")

            # The main (tour_content) path requires the source ZIP so the translated ZIP can
            # be assembled from the original HTML structure. If it is still missing here, fail
            # hard rather than crash inside _create_mobile_compatible_zip and insert a NULL row.
            if not original_zip_data:
                logging.error(f"Tour {original_tour_id} has tour_content but no source ZIP (audio_tour NULL, tour_blob_uri {tour_blob_uri!r}) — cannot build artifact")
                raise TranslationArtifactError(
                    f"tour {original_tour_id} has tour_content but no source ZIP artifact"
                )

            # Does the audio_tours table have a 'track' column? Guarded like the orchestrator
            # so the INSERT still works on a DB without the column.
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'audio_tours' AND column_name = 'track'
            """)
            has_track = cursor.fetchone() is not None
            source_track = None
            if has_track:
                cursor.execute("SELECT track FROM audio_tours WHERE id = %s", (original_tour_id,))
                _row = cursor.fetchone()
                source_track = _row[0] if _row else None
                logging.info(f"Source tour {original_tour_id} track = {source_track!r}; translation will inherit it")

            # Check if a USABLE translation already exists. GCS-TR1: a row is only a valid
            # cache hit if it actually has a downloadable artifact. Artifact-less rows (the
            # historic bug) are ignored here and regenerated below.
            cursor.execute(
                "SELECT id FROM audio_tours WHERE original_tour_id = %s AND content_language = %s "
                "AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)",
                (original_tour_id, target_language)
            )
            existing = cursor.fetchone()
            if existing:
                logging.info(f"Translation already exists: {existing[0]}")
                return existing[0], True  # [LOCAL-60] Return cache_hit=True
            
            # Translate tour name and request string
            translated_name = self.translate_text(original_tour[1], target_language)
            translated_request = self.translate_text(original_tour[2], target_language)
            
            # Split tour content into stops using the same logic as tour generation
            tour_stops = self._split_tour_content_into_stops(tour_content)
            logging.info(f"Split tour content into {len(tour_stops)} stops")
            
            # Translate each stop, then restore English metadata labels
            # [LOCAL-142] Single-pass optimization: strip nav fields from the raw
            # translation instead of translating a pre-stripped version separately.
            # This eliminates N translate_text calls per tour (one per stop).
            # [LOCAL-559R] Translate stops CONCURRENTLY with a bounded pool (max 5
            # workers). The LLM engine was ~102 s for 10 stops serially; per-stop calls
            # are independent and I/O-bound, so a small pool cuts wall time well under
            # 30 s while preserving output order (ThreadPoolExecutor.map is ordered).
            n_stops = len(tour_stops)
            max_workers = min(5, n_stops) if n_stops else 1
            with ThreadPoolExecutor(max_workers=max_workers) as _stop_pool:
                results = list(_stop_pool.map(
                    lambda args: self._translate_one_stop(args[0], args[1], n_stops, target_language),
                    list(enumerate(tour_stops))
                ))
            translated_stops = [r[0] for r in results]
            tts_texts = [r[1] for r in results]
            
            # Generate audio for each translated stop
            # Generate audio for each translated stop.
            # [LOCAL-559R] Polly calls are independent and I/O-bound — run them in the
            # same bounded pool (max 5), preserving order via map, to cut the serial tail.
            def _gen_audio(args):
                i, txt = args
                try:
                    audio_bytes = self.generate_audio(txt, target_language)
                    if audio_bytes:
                        logging.info(f"Generated audio for stop {i+1}/{len(tts_texts)}")
                        return audio_bytes
                    logging.warning(f"Failed to generate audio for stop {i+1}")
                    return None
                except Exception as e:
                    logging.error(f"Error generating audio for stop {i+1}: {e}")
                    return None

            _audio_workers = min(5, len(tts_texts)) if tts_texts else 1
            with ThreadPoolExecutor(max_workers=_audio_workers) as _audio_pool:
                translated_audio_files = list(_audio_pool.map(_gen_audio, list(enumerate(tts_texts))))
            
            # Create translated ZIP by preserving original HTML structure and replacing audio
            translated_zip_data = self._create_mobile_compatible_zip(
                original_zip_data, translated_name, translated_audio_files, target_language, translated_stops
            )

            # GCS-TR1: never insert a translation row without a real artifact. If the ZIP
            # builder failed (returns None) or produced empty bytes, fail hard — do NOT INSERT.
            if not translated_zip_data or len(translated_zip_data) == 0:
                logging.error(f"Tour {original_tour_id}: translated ZIP is empty/None — refusing to insert artifact-less row")
                raise TranslationArtifactError(
                    f"translated artifact build failed for tour {original_tour_id} ({target_language})"
                )

            # Store translated tour content for future reference
            translated_tour_content = "\n\n".join([
                f"Stop {i+1}: {stop}" for i, stop in enumerate(translated_stops)
            ])
            
            # Create new tour record.
            # [LOCAL-162] Carry the source tour's stops_count onto the translation.
            _original_stops_count = original_tour[10] if len(original_tour) > 10 else None
            # [GCS-TR1 + LOCAL-162] Track resolution: a translation inherits its source
            # tour's track (the service is shared by both Beta and Storied, so an env var
            # alone cannot know the caller). If the source row has no track (older rows),
            # fall back to this deployment's TOUR_TRACK env var, then to 'beta'.
            _env_track = os.getenv('TOUR_TRACK', 'beta').lower()
            if _env_track not in ('beta', 'storied'):
                _env_track = 'beta'
            _track = source_track if (has_track and source_track) else _env_track
            if has_track:
                cursor.execute("""
                    INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested,
                                           lat, lng, content_language, original_tour_id, tour_content, stops_count, track)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (
                    translated_name, translated_request, translated_zip_data, original_tour[4],
                    original_tour[5], original_tour[6], target_language, original_tour_id,
                    translated_tour_content, _original_stops_count, _track
                ))
            else:
                cursor.execute("""
                    INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested,
                                           lat, lng, content_language, original_tour_id, tour_content, stops_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (
                    translated_name, translated_request, translated_zip_data, original_tour[4],
                    original_tour[5], original_tour[6], target_language, original_tour_id,
                    translated_tour_content, _original_stops_count
                ))
            
            new_tour_id = cursor.fetchone()[0]
            conn.commit()
            
            logging.info(f"Created translated tour {new_tour_id} in {target_language} with {len(translated_stops)} stops (track={_track!r})")
            if self.translation_engine == 'llm':
                logging.info(f"[TRANSLATE-LLM] tour {new_tour_id} ({target_language}) total cost=${self._llm_tour_cost:.6f}")
            return new_tour_id, False  # [LOCAL-60] Fresh translation, cache_hit=False
            
        except TranslationArtifactError:
            # Hard failure: roll back so no partial/artifact-less row is committed, then
            # propagate so the endpoint can return a non-200 TRANSLATION_ARTIFACT_FAILED.
            conn.rollback()
            raise
        except Exception as e:
            logging.error(f"Tour translation with audio error: {e}")
            conn.rollback()
            return None, False
        finally:
            conn.close()
    
    def translate_zip_audio(self, zip_data, target_language):
        """Translate audio content in ZIP file - handles both embedded base64 and modernized (separate mp3) formats"""
        import tempfile
        import os
        import base64
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract original ZIP
                zip_path = os.path.join(temp_dir, "original.zip")
                with open(zip_path, 'wb') as f:
                    f.write(zip_data)
                
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Find and process HTML file
                html_files = [f for f in os.listdir(extract_dir) if f.endswith('.html')]
                if not html_files:
                    return zip_data  # Return original if no HTML
                
                html_file = os.path.join(extract_dir, html_files[0])
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Parse HTML and find embedded audio data
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Find all base64 audio data URLs
                audio_pattern = r'data:audio/[^;]+;base64,([A-Za-z0-9+/=]+)'
                audio_matches = re.findall(audio_pattern, html_content)
                
                logging.info(f"Found {len(audio_matches)} embedded audio data URLs")
                
                # Detect modernized ZIP format: separate audio_N.mp3 files
                existing_mp3s = sorted([f for f in os.listdir(extract_dir) if re.match(r'audio_\d+\.mp3', f)])
                is_modernized_format = len(existing_mp3s) > 0
                
                if is_modernized_format and not audio_matches:
                    # === MODERNIZED FORMAT: separate mp3 files ===
                    logging.info(f"Modernized ZIP format detected ({len(existing_mp3s)} mp3 files). Translating and replacing audio.")
                    
                    # For each audio_N.mp3, source the text from its sibling audio_N.txt
                    # (the exact narration script that produced the original mp3).
                    # Fall back to HTML paragraph extraction only if .txt is missing.
                    html_fallback_texts = None  # lazy-loaded if needed
                    
                    for i, mp3_filename in enumerate(existing_mp3s, start=1):
                        mp3_path = os.path.join(extract_dir, mp3_filename)
                        txt_path = os.path.join(extract_dir, f'audio_{i}.txt')
                        
                        # Determine source text for this stop
                        if os.path.exists(txt_path):
                            with open(txt_path, 'r', encoding='utf-8') as f:
                                source_text = f.read().strip()
                            logging.info(f"Stop {i}: sourced from audio_{i}.txt ({len(source_text)} chars)")
                        else:
                            # Fallback: extract from HTML paragraphs (imprecise, last resort)
                            if html_fallback_texts is None:
                                html_fallback_texts = []
                                for p in soup.find_all('p'):
                                    text = p.get_text().strip()
                                    if text and len(text) > 10:
                                        html_fallback_texts.append(text)
                                logging.warning(f"audio_{i}.txt missing — falling back to HTML paragraphs ({len(html_fallback_texts)} elements)")
                            
                            idx = i - 1
                            if idx < len(html_fallback_texts):
                                source_text = html_fallback_texts[idx]
                            else:
                                logging.warning(f"No text source for stop {i}, keeping original {mp3_filename}")
                                continue
                        
                        if not source_text:
                            logging.warning(f"Empty text for stop {i}, keeping original {mp3_filename}")
                            continue
                        
                        try:
                            translated_text = self.translate_text(source_text, target_language)
                            # Restore English Coordinates/Address lines so mobile app can parse map pins
                            translated_text_with_meta = self._restore_metadata_labels(source_text, translated_text, target_language)
                            # For TTS audio: strip nav/metadata fields (don't read coordinates aloud)
                            tts_source = self._strip_nav_fields_for_tts(source_text)
                            tts_translated = self.translate_text(tts_source, target_language)
                            audio_bytes = self.generate_audio(tts_translated, target_language)
                            if audio_bytes:
                                with open(mp3_path, 'wb') as f:
                                    f.write(audio_bytes)
                                logging.info(f"Replaced {mp3_filename} with translated audio ({len(audio_bytes)} bytes)")
                                # Also write translated script (with metadata) back to audio_N.txt
                                with open(txt_path, 'w', encoding='utf-8') as f:
                                    f.write(translated_text_with_meta)
                            else:
                                logging.warning(f"Polly returned no audio for stop {i}, keeping original {mp3_filename}")
                        except Exception as e:
                            logging.error(f"Error translating audio for stop {i}: {e}")
                    
                    # Translate visible HTML text content
                    for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        for h in soup.find_all(tag):
                            text = h.get_text().strip()
                            if text:
                                translated_text = self.translate_text(text, target_language)
                                h.clear()
                                h.append(NavigableString(translated_text))
                    
                    for p in soup.find_all('p'):
                        text = p.get_text().strip()
                        if text and len(text) > 5:
                            translated_text = self.translate_text(text, target_language)
                            p.clear()
                            p.append(NavigableString(translated_text))
                    
                    # Update title
                    title_tag = soup.find('title')
                    if title_tag and title_tag.get_text().strip():
                        translated_title = self.translate_text(title_tag.get_text(), target_language)
                        title_tag.string = translated_title
                    
                    # Save updated HTML
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(str(soup))
                    
                    # Update manifest.json with translated name
                    manifest_path = os.path.join(extract_dir, 'manifest.json')
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                manifest = json.load(f)
                            original_name = manifest.get('name', '')
                            if original_name:
                                translated_manifest_name = self.translate_text(original_name, target_language)
                                manifest['name'] = translated_manifest_name
                                manifest['short_name'] = translated_manifest_name[:12]
                            with open(manifest_path, 'w', encoding='utf-8') as f:
                                json.dump(manifest, f, indent=2, ensure_ascii=False)
                            logging.info(f"Updated manifest.json with translated name")
                        except Exception as e:
                            logging.warning(f"Could not update manifest.json: {e}")
                    
                    # Create new ZIP with translated content
                    new_zip_path = os.path.join(temp_dir, "translated.zip")
                    with zipfile.ZipFile(new_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                        for root, dirs, files in os.walk(extract_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arc_name = os.path.relpath(file_path, extract_dir)
                                zip_ref.write(file_path, arc_name)
                    
                    with open(new_zip_path, 'rb') as f:
                        translated_zip = f.read()
                    
                    logging.info(f"Successfully translated modernized ZIP with {len(existing_mp3s)} mp3 files replaced")
                    return translated_zip
                
                # === LEGACY FORMAT: embedded base64 audio ===
                # Extract text content for translation
                text_elements = []
                
                # Find paragraphs with substantial text
                paragraphs = soup.find_all('p')
                for p in paragraphs:
                    text = p.get_text().strip()
                    if text and len(text) > 10:
                        text_elements.append(text)
                
                # Find headings
                for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    headings = soup.find_all(tag)
                    for h in headings:
                        text = h.get_text().strip()
                        if text and len(text) > 5:
                            text_elements.append(text)
                
                # Find other text content in divs, spans, etc.
                for tag in ['div', 'span']:
                    elements = soup.find_all(tag)
                    for elem in elements:
                        # Only direct text, not nested
                        if elem.string and elem.string.strip() and len(elem.string.strip()) > 10:
                            text_elements.append(elem.string.strip())
                
                logging.info(f"Extracted {len(text_elements)} text elements for translation")
                
                # Generate translated audio for each text element
                translated_audio_data = []
                for i, text in enumerate(text_elements):
                    try:
                        # Translate text
                        translated_text = self.translate_text(text, target_language)
                        
                        # Generate audio using AWS Polly
                        audio_bytes = self.generate_audio(translated_text, target_language)
                        if audio_bytes:
                            # Encode as base64
                            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                            translated_audio_data.append(audio_base64)
                            logging.info(f"Generated translated audio {i+1}/{len(text_elements)} ({len(audio_base64)} chars)")
                        else:
                            # Keep original if translation fails
                            if i < len(audio_matches):
                                translated_audio_data.append(audio_matches[i])
                            logging.warning(f"Failed to generate audio for text element {i+1}")
                    except Exception as e:
                        # Keep original if translation fails
                        if i < len(audio_matches):
                            translated_audio_data.append(audio_matches[i])
                        logging.error(f"Error translating audio {i+1}: {e}")
                
                # Replace embedded audio data in HTML
                updated_html = html_content
                for i, (original_audio, translated_audio) in enumerate(zip(audio_matches, translated_audio_data)):
                    if original_audio != translated_audio:
                        # Replace the base64 data part only
                        original_data_url = f'data:audio/mp3;base64,{original_audio}'
                        translated_data_url = f'data:audio/mp3;base64,{translated_audio}'
                        updated_html = updated_html.replace(original_data_url, translated_data_url, 1)
                        logging.info(f"Replaced embedded audio data {i+1}")
                
                # Translate visible text content
                soup = BeautifulSoup(updated_html, 'html.parser')
                
                # Translate paragraphs
                for p in soup.find_all('p'):
                    if p.get_text().strip() and len(p.get_text().strip()) > 10:
                        original_text = p.get_text().strip()
                        translated_text = self.translate_text(original_text, target_language)
                        p.string = translated_text
                
                # Translate headings
                for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    for h in soup.find_all(tag):
                        if h.get_text().strip():
                            original_text = h.get_text().strip()
                            translated_text = self.translate_text(original_text, target_language)
                            h.string = translated_text
                
                # Update title
                title_tag = soup.find('title')
                if title_tag and title_tag.get_text().strip():
                    translated_title = self.translate_text(title_tag.get_text(), target_language)
                    title_tag.string = translated_title
                
                # Save updated HTML with translated audio
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(str(soup))
                
                # Create new ZIP with translated content
                new_zip_path = os.path.join(temp_dir, "translated.zip")
                with zipfile.ZipFile(new_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                    for root, dirs, files in os.walk(extract_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arc_name = os.path.relpath(file_path, extract_dir)
                            zip_ref.write(file_path, arc_name)
                
                # Read translated ZIP data
                with open(new_zip_path, 'rb') as f:
                    translated_zip = f.read()
                
                logging.info(f"Successfully translated ZIP with {len(audio_matches)} embedded audio files")
                return translated_zip
                    
        except Exception as e:
            logging.error(f"ZIP audio translation error: {e}")
            return original_zip_data  # Return original on error
    
    def translate_article(self, original_article_id, target_language):
        """Translate a newsletter article with audio generation matching English structure"""
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Get original article with major_points
            cursor.execute(
                "SELECT article_id, article_text, request_string, url, article_type, created_at, major_points FROM article_requests WHERE article_id = %s", 
                (original_article_id,)
            )
            original_article = cursor.fetchone()
            if not original_article:
                logging.error(f"Original article {original_article_id} not found")
                return None
            
            article_text = original_article[1]  # article_text column
            major_points = original_article[6]  # major_points column
            
            # Convert memoryview to string if needed
            if isinstance(article_text, memoryview):
                article_text = article_text.tobytes().decode('utf-8')
            elif isinstance(article_text, bytes):
                article_text = article_text.decode('utf-8')
            
            if not article_text or len(article_text.strip()) < 50:
                logging.error(f"Article {original_article_id} has insufficient content for translation")
                return None
            
            logging.info(f"Translating article with {len(article_text)} characters")
            
            # Check if translation already exists
            cursor.execute(
                "SELECT article_id FROM article_requests WHERE original_article_id = %s AND content_language = %s",
                (original_article_id, target_language)
            )
            existing = cursor.fetchone()
            if existing:
                logging.info(f"Translation already exists: {existing[0]}")
                return existing[0]
            
            # Parse major points if available
            topics = []
            if major_points:
                try:
                    if isinstance(major_points, list):
                        topics = major_points
                    else:
                        topics = json.loads(major_points)
                    logging.info(f"Found {len(topics)} topics for translation")
                except Exception as e:
                    logging.error(f"Failed to parse major_points: {e}")
                    topics = []
            
            # Translate article content and title
            translated_title = self.translate_text(original_article[2], target_language)  # request_string (title)
            translated_content = self.translate_text(article_text, target_language)
            
            # Translate each topic
            translated_topics = []
            for i, topic in enumerate(topics):
                try:
                    translated_topic = {
                        'summary': self.translate_text(topic.get('summary', ''), target_language),
                        'audio_text': self.translate_text(topic.get('audio_text', ''), target_language),
                        'segment_id': topic.get('segment_id', i),
                        'short_title': self.translate_text(topic.get('short_title', f'Topic {i+1}'), target_language)
                    }
                    translated_topics.append(translated_topic)
                    logging.info(f"Translated topic {i+1}: {translated_topic['short_title']}")
                except Exception as e:
                    logging.error(f"Error translating topic {i+1}: {e}")
                    translated_topics.append(topic)  # Keep original on error
            
            # Create mobile-compatible ZIP matching English structure exactly
            translated_zip_data = self._create_english_structure_zip(
                translated_title, translated_content, translated_topics, target_language
            )
            
            # Generate new article ID
            new_article_id = str(uuid.uuid4())
            
            # Store translated article in article_requests table
            if original_article[3]:  # If original URL exists
                translated_url = f"{original_article[3]}?lang={target_language}"
            else:
                # Generate unique URL if original is None
                translated_url = f"translated-article-{new_article_id}?lang={target_language}"
            
            cursor.execute("""
                INSERT INTO article_requests (article_id, article_text, request_string, url, 
                                            article_type, status, created_at, 
                                            content_language, original_article_id, major_points)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                new_article_id, translated_content, translated_title, translated_url,
                original_article[4], 'finished', original_article[5],
                target_language, original_article_id, json.dumps(translated_topics)
            ))
            
            # Store in news_audios table for download
            cursor.execute("""
                INSERT INTO news_audios (article_id, article_name, news_article, number_requested, article_type)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                new_article_id, translated_title, translated_zip_data, 1, original_article[4] or 'Others'
            ))
            
            conn.commit()
            
            logging.info(f"Created translated article {new_article_id} in {target_language} with {len(translated_topics)} topics")
            return new_article_id
            
        except Exception as e:
            logging.error(f"Article translation error: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def _create_english_structure_zip(self, title, content, topics, target_language):
        """Create ZIP matching exact English article structure with multiple MP3 files"""
        import tempfile
        import os
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_files = []
                
                # Split content into summary and full text (matching English format)
                parts = content.split('\n\nFull Article:', 1)
                if len(parts) == 2:
                    summary_text = parts[0].replace('Summary: ', '')
                    full_text = parts[1]  # Only the full article part
                else:
                    # If no "Full Article:" marker, create proper separation
                    sentences = content.split('. ')
                    if len(sentences) > 3:
                        summary_text = '. '.join(sentences[:2]) + '.'
                        full_text = '. '.join(sentences[2:])  # Remaining content as full article
                    else:
                        summary_text = content[:200] + '...'
                        full_text = content  # Use full content if too short to split
                
                # Generate summary audio (audio_1.mp3)
                summary_audio = self.generate_audio(f"Article Summary: {summary_text}", target_language)
                if summary_audio:
                    summary_file = os.path.join(temp_dir, 'audio_1.mp3')
                    with open(summary_file, 'wb') as f:
                        f.write(summary_audio)
                    audio_files.append(('audio_1.mp3', 'Summary'))
                
                # Generate topic audios (audio-1.mp3, audio-2.mp3, etc.)
                for i, topic in enumerate(topics):
                    try:
                        topic_text = topic.get('audio_text', topic.get('summary', f'Topic {i+1}'))
                        topic_audio = self.generate_audio(topic_text, target_language)
                        if topic_audio:
                            segment_id = topic.get('segment_id', i)
                            audio_filename = f'audio-{segment_id + 1}.mp3'
                            audio_path = os.path.join(temp_dir, audio_filename)
                            with open(audio_path, 'wb') as f:
                                f.write(topic_audio)
                            audio_files.append((audio_filename, topic.get('short_title', f'Topic {i+1}')))
                            logging.info(f"Generated {audio_filename} for topic: {topic.get('short_title', f'Topic {i+1}')}")
                    except Exception as e:
                        logging.error(f"Error generating audio for topic {i+1}: {e}")
                
                # Generate topics list audio (audio-topics.mp3) - KEEP VOICE COMMANDS IN ENGLISH
                if topics:
                    topics_text = "Here are the major topics covered in this article: "
                    for i, topic in enumerate(topics, 1):
                        short_title = topic.get('short_title', f'Topic {i}')
                        topics_text += f"{short_title}. "
                    topics_text += "You can ask me to play any of these topics by saying 'Play topic' followed by the number."
                    
                    # Translate topics text but preserve voice commands
                    translated_topics_text = self.translate_text(topics_text, target_language, preserve_voice_commands=True)
                    topics_audio = self.generate_audio(translated_topics_text, target_language)
                    if topics_audio:
                        topics_file = os.path.join(temp_dir, 'audio-topics.mp3')
                        with open(topics_file, 'wb') as f:
                            f.write(topics_audio)
                        audio_files.append(('audio-topics.mp3', 'Topics List'))
                
                # Generate help audio (audio-help.mp3) - KEEP COMPLETELY IN ENGLISH
                help_text = """Here are the voice commands you can use: 
                Say 'Play' to start or resume audio. Say 'Pause' to stop audio. 
                Say 'Next topic' or 'Previous topic' to navigate between sections. 
                Say 'Forward 10 seconds' or 'Backward 5 seconds' to skip within audio. 
                Say 'Repeat' to restart current audio from beginning. 
                Say 'Play topic' followed by a number or topic name to jump to specific sections. 
                Say 'Play summary' for article summary or 'Play full article' for complete text. 
                Say 'List major topics' to hear all available sections. 
                Say 'Next article' or 'Previous article' to switch between articles. 
                You can also say 'What are my options' anytime to hear this help again."""
                
                # Keep help text completely in English for mobile app compatibility
                help_audio = self.generate_audio(help_text, target_language)
                if help_audio:
                    help_file = os.path.join(temp_dir, 'audio-help.mp3')
                    with open(help_file, 'wb') as f:
                        f.write(help_audio)
                    audio_files.append(('audio-help.mp3', 'Help Commands'))
                
                # Generate full article audio (audio-99.mp3) - ONLY full article, not summary
                full_audio = self.generate_audio(full_text, target_language)  # Remove "Full Article:" prefix
                if full_audio:
                    full_file = os.path.join(temp_dir, 'audio-99.mp3')
                    with open(full_file, 'wb') as f:
                        f.write(full_audio)
                    audio_files.append(('audio-99.mp3', 'Full Article'))
                
                # Create HTML file matching English structure
                html_content = self._create_english_format_html(title, summary_text, full_text, topics, audio_files, target_language)
                html_file = os.path.join(temp_dir, 'index.html')
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                # Create search content file
                search_file = os.path.join(temp_dir, 'audiotours_search_content.txt')
                search_content = f"{title}\n\n{summary_text}\n\n{full_text}"
                with open(search_file, 'w', encoding='utf-8') as f:
                    f.write(search_content)
                
                # Create help commands text file for mobile app dialog (always English)
                help_commands_file = os.path.join(temp_dir, 'help_commands.txt')
                help_commands_text = """Voice Commands:

Say 'Play' to start or resume audio
Say 'Pause' to stop audio
Say 'Next topic' or 'Previous topic' to navigate
Say 'Forward 10 seconds' or 'Backward 5 seconds' to skip
Say 'Repeat' to restart current audio
Say 'Play topic' + number/name to jump to sections
Say 'Play summary' for article summary
Say 'Play full article' for complete text
Say 'List major topics' to hear all sections
Say 'Next article' or 'Previous article' to switch
Say 'What are my options' to hear this help again"""
                with open(help_commands_file, 'w', encoding='utf-8') as f:
                    f.write(help_commands_text)
                
                # Create short title if needed
                title_words = len(title.split())
                if title_words > 12:
                    short_title = ' '.join(title.split()[:12]) + '...'
                    short_title_file = os.path.join(temp_dir, 'audiotours_short_title.txt')
                    with open(short_title_file, 'w', encoding='utf-8') as f:
                        f.write(short_title)
                
                # Create ZIP file with same structure as English
                zip_path = os.path.join(temp_dir, 'article.zip')
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(html_file, 'index.html')
                    zipf.write(search_file, 'audiotours_search_content.txt')
                    zipf.write(help_commands_file, 'help_commands.txt')
                    if title_words > 12:
                        zipf.write(short_title_file, 'audiotours_short_title.txt')
                    for audio_file, _ in audio_files:
                        audio_path = os.path.join(temp_dir, audio_file)
                        if os.path.exists(audio_path):
                            zipf.write(audio_path, audio_file)
                
                # Read ZIP data
                with open(zip_path, 'rb') as f:
                    zip_data = f.read()
                
                logging.info(f"Created Russian article ZIP ({len(zip_data)} bytes) with {len(audio_files)} audio files matching English structure")
                return zip_data
                
        except Exception as e:
            logging.error(f"Error creating English structure ZIP: {e}")
            return None
    
    def _create_english_format_html(self, title, summary_text, full_text, topics, audio_files, target_language):
        """Generate HTML matching exact English article format"""
        
        # Create sections for each audio file
        audio_sections = ""
        for i, (audio_file, section_title) in enumerate(audio_files):
            # Determine proper audio ID based on file structure
            if audio_file == "audio_1.mp3":
                audio_id = "audio_1"
                section_class = "summary"
            elif audio_file == "audio-topics.mp3":
                audio_id = "audio-topics"
                # Hide topics list from UI - voice-only access
                audio_sections += f'<audio id="{audio_id}" preload="metadata" style="display:none;"><source src="{audio_file}" type="audio/mpeg"></audio>'
                continue
            elif audio_file == "audio-help.mp3":
                audio_id = "audio-help"
                # Hide help commands from UI - voice-only access
                audio_sections += f'<audio id="{audio_id}" preload="metadata" style="display:none;"><source src="{audio_file}" type="audio/mpeg"></audio>'
                continue
            elif audio_file == "audio-99.mp3":
                audio_id = "audio-99"
                section_class = "full-article"
            else:
                # Extract number from filename like audio-1.mp3, audio-2.mp3, etc.
                try:
                    if "-" in audio_file:
                        audio_num = audio_file.split("-")[1].split(".")[0]
                        audio_id = f"audio-{audio_num}"
                    else:
                        audio_num = audio_file.split("_")[1].split(".")[0] if "_" in audio_file else str(i+1)
                        audio_id = f"audio-{audio_num}"
                    section_class = "topic-section"
                except IndexError as e:
                    logging.error(f"Error parsing audio filename {audio_file}: {e}")
                    audio_id = f"audio-{i+1}"
                    section_class = "topic-section"
            
            # Hide major points from UI and auto-play - voice-only access
            if section_class == "topic-section":
                audio_sections += f'<audio id="{audio_id}" preload="metadata" style="display:none;"><source src="{audio_file}" type="audio/mpeg"></audio>'
                continue
            
            audio_sections += f'''
        <div class="section {section_class}">
            <h2>{section_title}</h2>
            <audio id="{audio_id}" controls preload="metadata">
                <source src="{audio_file}" type="audio/mpeg">
            </audio>
        </div>'''
        
        # Create HTML with exact English structure and JavaScript
        html = f'''<!DOCTYPE html>
<html lang="{target_language}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .article-container {{ max-width: 800px; margin: 0 auto; }}
        audio {{ width: 100%; margin: 20px 0; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .summary {{ background-color: #f0f8ff; }}
        .topic-section {{ background-color: #f5f5f5; }}
        .full-article {{ background-color: #f9f9f9; }}
    </style>
</head>
<body>
    <div class="article-container">
        <h1>{title}</h1>
        {audio_sections}
    </div>
    
    <script>
        let currentIndex = 0;
        let audioElements = [];
        let currentAudio = null;
        let autoPlayEnabled = true;
        let timerVariable = 0;
        let timeOutParameterGlobal = 100;
        let listIsBeingRead = false;
        
        function safeSetTimeout(func, timeout) {{
            if (timerVariable < 1) {{
                timerVariable++;
                setTimeout(() => {{
                    timerVariable--;
                    timeOutParameterGlobal = 100;
                    func();
                }}, timeout);
                return "DEBUG: Timer set for " + timeout + "ms";
            }}
            return "DEBUG: Timer blocked (active=" + timerVariable + ")";
        }}
        
        document.addEventListener('DOMContentLoaded', function() {{
            audioElements = Array.from(document.querySelectorAll('audio'));
            if (audioElements.length > 0) {{
                currentAudio = audioElements[0];
                safeSetTimeout(() => playAudioByIndex(0), 1000);
            }}
            
            audioElements.forEach((audio, index) => {{
                audio.addEventListener('play', function() {{
                    audioElements.forEach((otherAudio, otherIndex) => {{
                        if (otherIndex !== index && !otherAudio.paused) {{
                            otherAudio.pause();
                            otherAudio.currentTime = 0;
                        }}
                    }});
                    currentIndex = index;
                    currentAudio = audio;
                }});
                
                audio.addEventListener('ended', function() {{
                    if (autoPlayEnabled && index < audioElements.length - 1) {{
                        let nextIndex = index + 1;
                        // Skip hidden topic sections in auto-play sequence
                        while (nextIndex < audioElements.length && audioElements[nextIndex].style.display === 'none') {{
                            nextIndex++;
                        }}
                        if (nextIndex < audioElements.length) {{
                            safeSetTimeout(() => playAudioByIndex(nextIndex), 500);
                        }}
                    }}
                }});
            }});
        }});
        
        function playAudioByIndex(index) {{
            audioElements.forEach(audio => {{
                audio.pause();
                audio.currentTime = 0;
            }});
            
            if (index >= 0 && index < audioElements.length) {{
                currentIndex = index;
                currentAudio = audioElements[index];
                currentAudio.play();
                return true;
            }}
            return false;
        }}
        
        window.playAudio = function() {{
            if (currentAudio) {{
                currentAudio.play();
                return "DEBUG: Playing currentAudio (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No currentAudio set";
        }};
        
        window.pauseAudio = function() {{
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            return "DEBUG: All audio paused (currentIndex=" + currentIndex + ", time preserved)";
        }};
        
        window.resetVoiceControlState = function() {{
            listIsBeingRead = false;
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            return "DEBUG: Voice control state reset (listIsBeingRead=false, time preserved)";
        }};
        
        window.playPoint = function(pointNumber) {{
            const topicAudio = document.getElementById('audio-' + (pointNumber + 1));
            if (topicAudio) {{
                const topicIndex = Array.from(audioElements).indexOf(topicAudio);
                if (topicIndex >= 0) {{
                    return playAudioByIndex(topicIndex) ? 'Playing topic ' + pointNumber : 'Failed to play topic';
                }}
            }}
            return 'Topic ' + pointNumber + ' not found';
        }};
        
        window.seekForward = function(seconds) {{
            if (currentAudio) {{
                const maxTime = currentAudio.duration || 0;
                currentAudio.currentTime = Math.min(maxTime, currentAudio.currentTime + seconds);
                if (currentAudio.paused) {{
                    currentAudio.play();
                }}
                return "DEBUG: Seeked forward " + seconds + "s to " + currentAudio.currentTime.toFixed(1) + "s";
            }}
            return "ERROR: No current audio";
        }};
        
        window.seekBackward = function(seconds) {{
            if (currentAudio) {{
                currentAudio.currentTime = Math.max(0, currentAudio.currentTime - seconds);
                if (currentAudio.paused) {{
                    currentAudio.play();
                }}
                return "DEBUG: Seeked backward " + seconds + "s to " + currentAudio.currentTime.toFixed(1) + "s";
            }}
            return "ERROR: No current audio";
        }};
        
        window.listPoints = function() {{
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            
            const topicsAudio = document.getElementById('audio-topics');
            if (topicsAudio) {{
                topicsAudio.currentTime = 0;
                listIsBeingRead = true;
                topicsAudio.addEventListener('ended', function() {{
                    listIsBeingRead = false;
                }}, {{ once: true }});
                
                topicsAudio.play();
                return "DEBUG: Playing topics list (listIsBeingRead=true, duration=" + (topicsAudio.duration || 'unknown') + "s, other audio times preserved)";
            }}
            return "ERROR: Topics list not found";
        }};
        
        window.isListBeingRead = function() {{
            return listIsBeingRead ? "true" : "false";
        }};
        
        window.getTopicsAudioDuration = function() {{
            const topicsAudio = document.getElementById('audio-topics');
            return topicsAudio ? (topicsAudio.duration || 0).toString() : "0";
        }};
        
        window.showHelp = function() {{
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            
            const helpAudio = document.getElementById('audio-help');
            if (helpAudio) {{
                helpAudio.currentTime = 0;
                helpAudio.play();
                return "DEBUG: Playing help commands (duration=" + (helpAudio.duration || 'unknown') + "s)";
            }}
            return "ERROR: Help audio not found";
        }};
        
        window.playFullArticle = function() {{
            const fullArticleAudio = document.getElementById('audio-99');
            if (fullArticleAudio) {{
                const fullIndex = Array.from(audioElements).indexOf(fullArticleAudio);
                if (fullIndex >= 0) {{
                    return playAudioByIndex(fullIndex) ? 'Playing full article' : 'Failed to play full article';
                }}
            }}
            return 'Full article not found';
        }};
        
        window.repeatTopic = function() {{
            if (currentAudio) {{
                currentAudio.currentTime = 0;
                return "DEBUG: Reset currentAudio to 0s (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No currentAudio to repeat";
        }};
        
        window.nextTopic = function() {{
            let nextIndex = currentIndex + 1;
            while (nextIndex < audioElements.length && audioElements[nextIndex].style.display === 'none') {{
                nextIndex++;
            }}
            
            if (nextIndex < audioElements.length) {{
                currentIndex = nextIndex;
                currentAudio = audioElements[currentIndex];
                return "DEBUG: Advanced to next (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No next topic available";
        }};
        
        window.previousTopic = function() {{
            let prevIndex = currentIndex - 1;
            while (prevIndex >= 0 && audioElements[prevIndex].style.display === 'none') {{
                prevIndex--;
            }}
            
            if (prevIndex >= 0) {{
                currentIndex = prevIndex;
                currentAudio = audioElements[currentIndex];
                return "DEBUG: Moved to previous (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No previous topic available";
        }};
    </script>
</body>
</html>'''
        return html
    # Fields that should not be spoken aloud — same set as Fix A in tour_generation_modernized.py
    _NAV_FIELD_PREFIXES = [
        'Address:', 'Coordinates:', 'Type/Specialty:', 'Specific Examples:',
        'Operational Details:'
    ]

    def _strip_nav_fields_for_tts(self, stop_text):
        """Remove structured metadata lines from stop text before sending to Polly.
        Keeps: Name, Orientation (full), and all narrative paragraphs.
        Strips: Address, Coordinates, Type/Specialty, Specific Examples, Operational Details."""
        lines = stop_text.split('\n')
        clean_lines = []
        skip_next_blank = False
        for line in lines:
            stripped = line.strip()
            is_nav = any(
                re.match(rf'^{re.escape(prefix)}', stripped, re.IGNORECASE)
                for prefix in self._NAV_FIELD_PREFIXES
            )
            if is_nav:
                skip_next_blank = True
                continue
            if skip_next_blank and stripped == '':
                skip_next_blank = False
                continue
            skip_next_blank = False
            clean_lines.append(line)
        return '\n'.join(clean_lines).strip()

    def _strip_nav_fields_from_translated(self, original_text, translated_text):
        """Strip nav fields from an already-translated stop using positional template.

        [LOCAL-142] Eliminates the second translation pass by stripping nav fields from
        the raw translation output rather than translating a pre-stripped English version.

        Approach (positional template):
          1. Split both English source and translated text into lines.
          2. In the English source, identify which line indices hold nav fields
             (and their trailing blank lines).
          3. If the translated text has the same line count, drop those same indices.
          4. If line counts diverge (translation merged/split lines), return None
             to signal the caller to fall back to the two-pass approach.

        Args:
            original_text: English source text for the stop.
            translated_text: Raw translation output (BEFORE _restore_metadata_labels).

        Returns:
            Stripped TTS text (str) on success, or None if fallback is needed.
        """
        en_lines = original_text.split('\n')
        tr_lines = translated_text.split('\n')

        if len(en_lines) != len(tr_lines):
            return None  # Line count mismatch → caller must fall back

        # Identify indices to drop: nav field lines and their trailing blank line
        drop_indices = set()
        skip_next_blank = False
        for i, line in enumerate(en_lines):
            stripped = line.strip()
            is_nav = any(
                re.match(rf'^{re.escape(prefix)}', stripped, re.IGNORECASE)
                for prefix in self._NAV_FIELD_PREFIXES
            )
            if is_nav:
                drop_indices.add(i)
                skip_next_blank = True
                continue
            if skip_next_blank and stripped == '':
                drop_indices.add(i)
                skip_next_blank = False
                continue
            skip_next_blank = False

        # Drop the same indices from the translated text
        clean_lines = [tr_lines[i] for i in range(len(tr_lines)) if i not in drop_indices]
        return '\n'.join(clean_lines).strip()

    def _split_tour_content_into_stops(self, tour_content):
        """Split tour content into individual stops using the same logic as tour generation"""
        
        # Split content by stops using regex pattern
        stops = re.split(r'\n\s*Stop\s+(\d+):', tour_content)
        
        text_content = []
        
        if len(stops) > 1:
            stops = stops[1:]  # Remove title part
            
            # Process stops in pairs (number, content)
            for i in range(0, len(stops), 2):
                if i + 1 < len(stops):
                    stop_num = stops[i].strip()
                    stop_content = stops[i+1].strip()
                    
                    # Clean up the content
                    if stop_content:
                        text_content.append(stop_content)
        
        # If no stops found, try alternative splitting
        if not text_content:
            # Try splitting by numbered sections
            lines = tour_content.split('\n')
            current_stop = []
            
            for line in lines:
                line = line.strip()
                if re.match(r'^\d+\.', line) or re.match(r'^Stop \d+', line):
                    if current_stop:
                        text_content.append('\n'.join(current_stop))
                        current_stop = []
                    current_stop.append(line)
                elif line and current_stop:
                    current_stop.append(line)
            
            # Add the last stop
            if current_stop:
                text_content.append('\n'.join(current_stop))
        
        # If still no content, use the entire text as one stop
        if not text_content and tour_content.strip():
            text_content = [tour_content.strip()]
        
        return text_content
    
    def _create_mobile_compatible_zip(self, original_zip_data, translated_name, audio_files, target_language, translated_stops):
        """Create mobile-compatible ZIP by preserving original HTML structure and replacing audio"""
        import tempfile
        import os
        import base64
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract original ZIP
                original_zip_path = os.path.join(temp_dir, "original.zip")
                with open(original_zip_path, 'wb') as f:
                    f.write(original_zip_data)
                
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir)
                
                with zipfile.ZipFile(original_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Find and process HTML file
                html_files = [f for f in os.listdir(extract_dir) if f.endswith('.html')]
                if not html_files:
                    logging.error("No HTML file found in original ZIP")
                    return original_zip_data
                
                html_file_path = os.path.join(extract_dir, html_files[0])
                with open(html_file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Parse HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Update title with translated name
                title_tag = soup.find('title')
                if title_tag:
                    title_tag.string = translated_name
                
                # Find all base64 audio data URLs in the HTML - try multiple patterns
                audio_patterns = [
                    r'data:audio/[^;]+;base64,([A-Za-z0-9+/=]+)',  # Standard pattern
                    r'data:audio/mp3;base64,([A-Za-z0-9+/=]+)',     # MP3 specific
                    r'data:audio/mpeg;base64,([A-Za-z0-9+/=]+)',    # MPEG specific
                    r'src="data:audio/[^"]+;base64,([A-Za-z0-9+/=]+)"'  # With src attribute
                ]
                
                audio_matches = []
                for pattern in audio_patterns:
                    matches = re.findall(pattern, html_content)
                    if matches:
                        audio_matches.extend(matches)
                        logging.info(f"Found {len(matches)} audio URLs with pattern: {pattern[:30]}...")
                
                # Remove duplicates while preserving order
                seen = set()
                unique_audio_matches = []
                for match in audio_matches:
                    if match not in seen:
                        seen.add(match)
                        unique_audio_matches.append(match)
                
                audio_matches = unique_audio_matches
                
                logging.info(f"Found {len(audio_matches)} embedded audio data URLs")
                logging.info(f"Have {len(audio_files)} translated audio files")
                
                # Replace embedded audio data with translated audio
                updated_html = str(soup)
                
                # Detect modernized ZIP format: separate audio_N.mp3 files (not embedded base64)
                existing_mp3s = sorted([f for f in os.listdir(extract_dir) if re.match(r'audio_\d+\.mp3', f)])
                is_modernized_format = len(existing_mp3s) > 0

                if not audio_matches and audio_files:
                    if is_modernized_format:
                        # Modernized format: overwrite audio_1.mp3, audio_2.mp3 ... with translated Polly bytes
                        logging.info(f"Modernized ZIP format detected ({len(existing_mp3s)} mp3 files). Replacing with translated audio.")
                        if len(audio_files) != len(existing_mp3s):
                            logging.warning(f"Stop count mismatch: {len(audio_files)} translated stops vs {len(existing_mp3s)} original mp3s — some stops may keep English audio")
                        for i, translated_audio_bytes in enumerate(audio_files):
                            mp3_filename = f'audio_{i+1}.mp3'
                            mp3_path = os.path.join(extract_dir, mp3_filename)
                            if translated_audio_bytes:
                                with open(mp3_path, 'wb') as f:
                                    f.write(translated_audio_bytes)
                                logging.info(f"Wrote translated audio to {mp3_filename}")
                            else:
                                logging.warning(f"No translated audio for stop {i+1}, keeping original {mp3_filename}")
                        # BUG 1 FIX: Translate HTML text (h1–h6, p) — audio replacement above
                        # only swaps MP3 files; the HTML visible text was left in English.
                        # Use h.clear() + h.append(NavigableString(...)) instead of h.string =
                        # so headings with nested tags (e.g. <h3><span>…</span>) are handled safely.
                        translated_count = 0
                        for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            for h in soup.find_all(tag):
                                text = h.get_text().strip()
                                if text:
                                    h.clear()
                                    h.append(NavigableString(self.translate_text(text, target_language)))
                                    translated_count += 1
                        for p in soup.find_all('p'):
                            text = p.get_text().strip()
                            if text and len(text) > 5:
                                p.clear()
                                p.append(NavigableString(self.translate_text(text, target_language)))
                                translated_count += 1
                        logging.info(f"Translated {translated_count} HTML text elements in modernized ZIP")
                        updated_html = str(soup)
                    else:
                        # Legacy format without embedded audio — translate HTML text only
                        logging.info("No embedded audio and no separate mp3 files found, translating HTML text only")
                        translated_count = 0
                        for p in soup.find_all('p'):
                            text = p.get_text().strip()
                            if text and len(text) > 5:
                                p.clear()
                                p.append(NavigableString(self.translate_text(text, target_language)))
                                translated_count += 1
                        for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            for h in soup.find_all(tag):
                                text = h.get_text().strip()
                                if text:
                                    h.clear()
                                    h.append(NavigableString(self.translate_text(text, target_language)))
                                    translated_count += 1
                        logging.info(f"Translated {translated_count} HTML elements")
                        updated_html = str(soup)
                    
                else:
                    # Original method for embedded base64 audio
                    for i, (original_audio_b64, translated_audio_bytes) in enumerate(zip(audio_matches, audio_files)):
                        if translated_audio_bytes:
                            try:
                                # Encode translated audio as base64
                                translated_audio_b64 = base64.b64encode(translated_audio_bytes).decode('utf-8')
                                
                                # Replace the base64 data in the HTML
                                original_data_url = f'data:audio/mp3;base64,{original_audio_b64}'
                                translated_data_url = f'data:audio/mp3;base64,{translated_audio_b64}'
                                
                                updated_html = updated_html.replace(original_data_url, translated_data_url, 1)
                                logging.info(f"Replaced embedded audio data {i+1}/{len(audio_matches)}")
                                
                            except Exception as e:
                                logging.error(f"Error replacing audio {i+1}: {e}")
                        else:
                            logging.warning(f"No translated audio available for stop {i+1}, keeping original")
                
                # Save updated HTML
                with open(html_file_path, 'w', encoding='utf-8') as f:
                    f.write(updated_html)
                
                # Update manifest.json if it exists
                manifest_path = os.path.join(extract_dir, 'manifest.json')
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            manifest = json.load(f)
                        
                        manifest['name'] = translated_name
                        manifest['short_name'] = translated_name[:12]
                        
                        with open(manifest_path, 'w', encoding='utf-8') as f:
                            json.dump(manifest, f, indent=2)
                        
                        logging.info("Updated manifest.json with translated name")
                    except Exception as e:
                        logging.warning(f"Could not update manifest.json: {e}")
                
                # Add translated tour content as text file for reference
                if audio_files:
                    # Create full Russian tour content file
                    tour_content_text = "\n\n".join([
                        f"Stop {i+1}: {stop}" for i, stop in enumerate(translated_stops)
                    ])
                    content_file = os.path.join(extract_dir, 'tour_content.txt')
                    with open(content_file, 'w', encoding='utf-8') as f:
                        f.write(tour_content_text)
                    
                    # Create individual translated stop text files (1-indexed to match audio_N.mp3)
                    for i, translated_stop in enumerate(translated_stops, 1):
                        stop_file = os.path.join(extract_dir, f'audio_{i}.txt')
                        with open(stop_file, 'w', encoding='utf-8') as f:
                            f.write(translated_stop)
                
                # Create new ZIP with translated content
                new_zip_path = os.path.join(temp_dir, "translated.zip")
                with zipfile.ZipFile(new_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(extract_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arc_name = os.path.relpath(file_path, extract_dir)
                            zipf.write(file_path, arc_name)
                
                # Read translated ZIP data
                with open(new_zip_path, 'rb') as f:
                    translated_zip = f.read()
                
                logging.info(f"Created mobile-compatible translated ZIP ({len(translated_zip)} bytes)")
                return translated_zip
                
        except Exception as e:
            logging.error(f"Error creating mobile-compatible ZIP: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            # GCS-TR1: signal failure instead of passing the original (or None) through.
            # The historic bug returned original_zip_data here (None for R2-migrated tours),
            # and the caller then INSERTed an artifact-less row that 404'd. Returning None
            # makes the caller raise TranslationArtifactError and skip the INSERT.
            return None
    
    def _generate_translated_html(self, tour_name, translated_stops, audio_files, target_language):
        """Generate HTML with embedded translated audio data.

        NOTE (2026-05-18): Dead code — no callers in the codebase as of commit 792487c.
        The legacy fallback _translate_tour_from_zip() uses translate_zip_audio() instead.
        Kept to keep the A#55 merge diff focused; slated for removal in a post-merge
        cleanup commit. Map-button logic here is defensive — correct if ever called,
        but currently unreachable.
        """
        import base64
        
        html = f'''<!DOCTYPE html>
<html lang="{target_language}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{tour_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .tour-header {{ text-align: center; margin-bottom: 30px; }}
        .audio-item {{ margin: 20px 0; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stop-title {{ color: #2c3e50; margin-bottom: 10px; }}
        .stop-content {{ margin: 15px 0; line-height: 1.6; }}
        audio {{ width: 100%; margin-top: 10px; }}
        .language-indicator {{ background: #3498db; color: white; padding: 5px 10px; border-radius: 15px; font-size: 12px; }}
        .map-btn {{ background: #2c3e50; border: none; border-radius: 50%; width: 36px; height: 36px;
                    font-size: 20px; line-height: 1;
                    cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
                    margin-left: 8px; vertical-align: middle; }}
    </style>
</head>
<body>
    <script>
        function openMap(stopNum) {{
            if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {{
                window.flutter_inappwebview.callHandler('openMap', {{stop: stopNum}});
            }}
        }}
    </script>
    <div class="tour-header">
        <h1>{tour_name}</h1>
        <span class="language-indicator">{target_language.upper()}</span>
    </div>'''
        
        for i, (stop_text, audio_data) in enumerate(zip(translated_stops, audio_files)):
            # Extract stop title from text content
            lines = stop_text.split('\n')
            stop_title = lines[0].strip() if lines else f"Stop {i+1}"
            
            # Map button — only if stop has coordinates
            map_button = ''
            if re.search(r'^Coordinates:\s*[-\d.]+\s*,\s*[-\d.]+', stop_text, re.IGNORECASE | re.MULTILINE):
                map_button = f'<button class="map-btn" onclick="openMap({i+1})" title="View on map">🗺</button>'
            
            # Create audio data URL if audio is available
            audio_element = ""
            if audio_data:
                try:
                    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                    audio_data_url = f'data:audio/mp3;base64,{audio_base64}'
                    audio_element = f'''
        <audio id="audio{i}" controls preload="metadata">
            <source src="{audio_data_url}" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>'''
                except Exception as e:
                    logging.error(f"Error encoding audio for stop {i+1}: {e}")
                    audio_element = f'<p><em>Audio not available for this stop</em></p>'
            else:
                audio_element = f'<p><em>Audio generation failed for this stop</em></p>'
            
            html += f'''
    <div class="audio-item">
        <h3 class="stop-title">{stop_title}</h3>
        {map_button}
        <div class="stop-content">
            <p>{stop_text.replace(chr(10), '</p><p>')}</p>
        </div>{audio_element}
    </div>'''
        
        # Add voice control JavaScript
        html += '''
    
    <script>
        let audioElements = [];
        let currentStopIndex = 0;
        
        window.playAudio = function() {
            audioElements.forEach((audio, index) => {
                if (index !== currentStopIndex) {
                    audio.pause();
                    audio.currentTime = 0;
                }
            });
            
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].play();
                return "Success: Playing stop-" + currentStopIndex;
            }
            return "Error: No audio to play";
        };
        
        window.pauseAudio = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].pause();
                return "Success: Audio paused";
            }
            return "Error: No audio to pause";
        };
        
        window.nextStop = function() {
            if (currentStopIndex < audioElements.length - 1) {
                currentStopIndex++;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at last stop";
        };
        
        window.previousStop = function() {
            if (currentStopIndex > 0) {
                currentStopIndex--;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at first stop";
        };
        
        document.addEventListener('DOMContentLoaded', function() {
            const audios = document.querySelectorAll('audio');
            audioElements = Array.from(audios);
            
            audioElements.forEach((audio, index) => {
                audio.addEventListener('play', function() {
                    currentStopIndex = index;
                });
            });
        });
    </script>
</body>
</html>'''
        return html
    
    def _translate_tour_from_zip(self, original_tour, target_language, zip_data_override=None):
        """Fallback method for tours without stored content - uses old ZIP extraction method"""
        logging.info("Using fallback ZIP extraction method for tour translation")
        
        # Translate tour name and request string
        translated_name = self.translate_text(original_tour[1], target_language)
        translated_request = self.translate_text(original_tour[2], target_language)
        
        # Process ZIP file for audio translation — use override if provided (e.g., from R2)
        original_zip_data = zip_data_override if zip_data_override else original_tour[3]
        if not original_zip_data:
            logging.error(f"Tour {original_tour[0]} has no ZIP data (audio_tour is NULL) — cannot translate")
            return None
        
        # Convert memoryview/buffer to bytes if needed
        if hasattr(original_zip_data, 'tobytes'):
            original_zip_data = original_zip_data.tobytes()
        elif not isinstance(original_zip_data, bytes):
            original_zip_data = bytes(original_zip_data)
        
        translated_zip_data = self.translate_zip_audio(original_zip_data, target_language)

        # GCS-TR1: never insert a translation row without a real artifact.
        if not translated_zip_data or len(translated_zip_data) == 0:
            logging.error(f"Tour {original_tour[0]}: ZIP fallback produced empty/None artifact — refusing to insert")
            raise TranslationArtifactError(
                f"ZIP-fallback artifact build failed for tour {original_tour[0]} ({target_language})"
            )

        # Create new tour record
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            # [LOCAL-162] Carry the source tour's stops_count onto the translation.
            _fallback_stops_count = original_tour[10] if len(original_tour) > 10 else None
            # [GCS-TR1] Does the audio_tours table have a 'track' column? Guarded so the
            # INSERT still works on a DB without the column.
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'audio_tours' AND column_name = 'track'
            """)
            has_track = cursor.fetchone() is not None
            source_track = None
            if has_track:
                cursor.execute("SELECT track FROM audio_tours WHERE id = %s", (original_tour[0],))
                _row = cursor.fetchone()
                source_track = _row[0] if _row else None
            # [GCS-TR1 + LOCAL-162] Inherit the source tour's track; fall back to this
            # deployment's TOUR_TRACK env var, then to 'beta', when the source has none.
            _env_track = os.getenv('TOUR_TRACK', 'beta').lower()
            if _env_track not in ('beta', 'storied'):
                _env_track = 'beta'
            _track = source_track if (has_track and source_track) else _env_track
            if has_track:
                cursor.execute("""
                    INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested,
                                           lat, lng, content_language, original_tour_id, stops_count, track)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (
                    translated_name, translated_request, translated_zip_data, original_tour[4],
                    original_tour[5], original_tour[6], target_language, original_tour[0],
                    _fallback_stops_count, _track
                ))
            else:
                cursor.execute("""
                    INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested,
                                           lat, lng, content_language, original_tour_id, stops_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (
                    translated_name, translated_request, translated_zip_data, original_tour[4],
                    original_tour[5], original_tour[6], target_language, original_tour[0],
                    _fallback_stops_count
                ))
            
            new_tour_id = cursor.fetchone()[0]
            conn.commit()
            
            logging.info(f"Created translated tour {new_tour_id} in {target_language} using ZIP fallback (track={_track!r})")
            return new_tour_id
            
        except TranslationArtifactError:
            conn.rollback()
            raise
        except Exception as e:
            logging.error(f"Fallback tour translation error: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

# Initialize translation service
translation_service = TranslationService()

def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.after_request
def after_request(response):
    return add_cors_headers(response)

@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    if request.method == 'OPTIONS':
        return make_response()
    return jsonify({"status": "healthy", "service": "translation"})

@app.route('/translate-with-audio', methods=['POST', 'OPTIONS'])
def translate_content_with_audio():
    if request.method == 'OPTIONS':
        return make_response()
    
    data = request.json
    content_id = data.get('content_id')
    content_type = data.get('content_type')  # 'tour' or 'article'
    languages = data.get('languages', ['en'])
    
    results = {}
    had_artifact_failure = False
    for lang in languages:
        if lang == 'en':
            results[lang] = {'status': 'original', 'id': content_id}
            continue

        # [LOCAL-60] translate_tour_with_audio returns (id, cache_hit); translate_article
        # returns a bare id. [GCS-TR1] both may raise TranslationArtifactError when no
        # downloadable artifact could be produced — surface that as a hard failure (non-200)
        # instead of a silent 200 hiding an artifact-less/404-ing row.
        _cache_hit = False
        try:
            if content_type == 'tour':
                translated_id, _cache_hit = translation_service.translate_tour_with_audio(content_id, lang)
            elif content_type == 'article':
                translated_id = translation_service.translate_article(content_id, lang)
            else:
                translated_id = None
        except TranslationArtifactError as e:
            logging.error(f"Artifact failure translating {content_type} {content_id} to {lang}: {e}")
            had_artifact_failure = True
            results[lang] = {
                'status': 'failed',
                'id': None,
                'error_code': TranslationArtifactError.error_code,
                'error': str(e),
            }
            continue

        
        if translated_id:
            # Include translated tour_name so the mobile app can display the correct title
            translated_name = None
            try:
                conn = translation_service.get_db_connection()
                cur = conn.cursor()
                table = 'audio_tours' if content_type == 'tour' else 'article_requests'
                name_col = 'tour_name' if content_type == 'tour' else 'request_string'
                cur.execute(f"SELECT {name_col} FROM {table} WHERE id = %s", (translated_id,))
                row = cur.fetchone()
                if row:
                    translated_name = row[0]
                cur.close()
                conn.close()
            except Exception as e:
                logging.warning(f"Could not fetch translated name for {translated_id}: {e}")
            
            result_entry = {'status': 'translated', 'id': translated_id, 'cache_hit': _cache_hit}
            if translated_name:
                result_entry['name'] = translated_name
            results[lang] = result_entry
        else:
            results[lang] = {'status': 'failed', 'id': None}
    
    status_code = 502 if had_artifact_failure else 200
    return jsonify({
        'status': 'completed' if not had_artifact_failure else 'error',
        'error_code': TranslationArtifactError.error_code if had_artifact_failure else None,
        'translations': results
    }), status_code
@app.route('/translate', methods=['POST', 'OPTIONS'])
def translate_content():
    if request.method == 'OPTIONS':
        return make_response()
    
    data = request.json
    content_id = data.get('content_id')
    content_type = data.get('content_type')  # 'tour' or 'article'
    languages = data.get('languages', ['en'])
    
    results = {}
    for lang in languages:
        if lang == 'en':
            results[lang] = {'status': 'original', 'id': content_id}
            continue
            
        if content_type == 'tour':
            translated_id = translation_service.translate_tour(content_id, lang)
        else:
            translated_id = translation_service.translate_article(content_id, lang)
        
        if translated_id:
            results[lang] = {'status': 'translated', 'id': translated_id}
        else:
            results[lang] = {'status': 'failed', 'id': None}
    
    return jsonify({
        'status': 'completed',
        'translations': results
    })

@app.route('/supported-languages', methods=['GET', 'OPTIONS'])
def get_supported_languages():
    if request.method == 'OPTIONS':
        return make_response()
    
    conn = translation_service.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM supported_languages WHERE enabled = TRUE ORDER BY language_code")
        languages = cursor.fetchall()
        
        result = []
        for lang in languages:
            result.append({
                'code': lang[0],
                'name': lang[1],
                'voice': lang[2],
                'enabled': lang[3]
            })
        
        return jsonify({'languages': result})
    finally:
        conn.close()

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5030'))
    app.run(host='0.0.0.0', port=port, debug=False)