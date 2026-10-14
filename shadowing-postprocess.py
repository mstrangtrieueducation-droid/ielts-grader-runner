"""Offline formatting only. No network, model calls, score changes or new evidence."""
import json
import re
import sys
import unicodedata


def normalize(payload):
    text = payload['text'].strip().lstrip('\ufeff')
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.I)
        text = re.sub(r'\s*```$', '', text)
    changes = []
    try:
        grade = json.loads(text)
    except json.JSONDecodeError:
        # Ignore prose surrounding ONE complete JSON assessment. Do not
        # manufacture missing JSON fields or choose between multiple grades.
        candidates = []
        decoder = json.JSONDecoder()
        for match in re.finditer(r'\{', text):
            try:
                value, _ = decoder.raw_decode(text[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and isinstance(value.get('assessable'), bool) and isinstance(value.get('sections'), list):
                candidates.append(value)
        if len(candidates) != 1:
            raise ValueError('one complete assessment object required')
        grade = candidates[0]
        changes.append('surrounding_response_prose_removed')

    def clean(value):
        if isinstance(value, str):
            return unicodedata.normalize('NFC', value).replace('\r\n', '\n').replace('\r', '\n').strip()
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value

    grade = clean(grade)
    if not isinstance(grade, dict):
        raise ValueError('object required')
    fixed = payload.get('fixedLedger')
    if fixed is not None:
        if fixed.get('version') not in ('shadow-single-pass-fixed-ledger-v1', 'shadow-single-pass-explicit-coverage-v2'):
            raise ValueError('invalid fixed ledger version')
        for name in ('units', 'prosody', 'fluency'):
            block = grade.get('scoreLedger', {}).get(name)
            if not isinstance(block, dict) or not isinstance(block.get('errors'), list) or not isinstance(block.get('unclearIndexes'), list) or not isinstance(fixed.get(name), list) or not fixed[name]:
                raise ValueError('incomplete acoustic verdicts')
            block['targets'] = list(fixed[name])
        changes.append('request_reference_targets_restored')
    def word(value):
        if not isinstance(value, str):
            return value
        tokens = re.findall(r"[a-z]+(?:['’\-][a-z]+)*", value.lower())
        if len(tokens) == 1:
            if tokens[0] != value:
                changes.append('single_word_punctuation')
            return tokens[0]
        return value

    units = grade.get('scoreLedger', {}).get('units')
    # Losslessly expand a punctuation-joined correct group (e.g. ha,ha,ha).
    # Never split an incorrect or unclear group: its individual verdicts would
    # be unknown. Remap every later evidence index without adding evidence.
    if isinstance(units, dict) and isinstance(units.get('targets'), list):
        targets = units['targets']
        errors = units.get('errors', [])
        unclear = units.get('unclearIndexes', [])
        blocked = {e.get('unitIndex') for e in errors} | set(unclear)
        outcomes = units.get('outcomes')
        mapping, expanded, expanded_outcomes = {}, [], []
        for index, target in enumerate(targets):
            mapping[index] = len(expanded)
            tokens = re.findall(r"[a-z]+(?:['’\-][a-z]+)*", target.lower()) if isinstance(target, str) else []
            is_correct = outcomes is None or (isinstance(outcomes, str) and len(outcomes) == len(targets) and outcomes[index] == 'C')
            parts = tokens if len(tokens) > 1 and index not in blocked and is_correct else [target]
            expanded.extend(parts)
            if isinstance(outcomes, str) and len(outcomes) == len(targets):
                expanded_outcomes.extend(outcomes[index] for _ in parts)
        if len(expanded) != len(targets):
            units['targets'] = expanded
            for error in errors:
                if error.get('unitIndex') in mapping:
                    error['unitIndex'] = mapping[error['unitIndex']]
            units['unclearIndexes'] = [mapping.get(i, i) for i in unclear]
            if isinstance(outcomes, str) and len(outcomes) == len(targets):
                units['outcomes'] = ''.join(expanded_outcomes)
            changes.append('correct_group_tokenization')
    if isinstance(units, dict) and isinstance(units.get('targets'), list):
        units['targets'] = [word(v) for v in units['targets']]
    elif isinstance(units, list):
        for unit in units:
            if isinstance(unit, dict) and 'target' in unit:
                unit['target'] = word(unit['target'])
    for entry in [*grade.get('evidence', []), *grade.get('uncertainty', [])]:
        if entry.get('type') in ('pronunciation', 'content') and entry.get('word'):
            entry['word'] = word(entry['word'])
        stamp = entry.get('time')
        if isinstance(stamp, str):
            m = re.fullmatch(r'(\d{1,2}):(\d{1,2})(\.\d+)?', stamp)
            if m and int(m[2]) < 60:
                entry['time'] = f'{int(m[1]):02}:{int(m[2]):02}{m[3] or ""}'
                if entry['time'] != stamp:
                    changes.append('timestamp_padding')
        ipa = entry.get('ipa')
        if isinstance(ipa, str) and ipa and '/' not in ipa:
            bare = ipa[1:-1] if ipa.startswith('[') and ipa.endswith(']') else ipa
            if not re.search(r'[\s\n<>]', bare):
                entry['ipa'] = '/' + bare + '/'
                changes.append('ipa_delimiters')
    # Fix a metadata index only when all linked evidence names the same target
    # and that target occurs exactly once. Repeated or uncertain targets stay
    # untouched; no error, deduction or coverage claim is manufactured.
    if isinstance(units, dict):
        targets = units.get('targets', [])
        evidence = grade.get('evidence', [])
        for error in units.get('errors', []):
            indexes = error.get('evidenceIndexes', [])
            if not indexes or any(not isinstance(i, int) or i < 0 or i >= len(evidence) for i in indexes):
                continue
            words = {evidence[i].get('word') for i in indexes}
            if len(words) != 1 or not next(iter(words)):
                continue
            target = next(iter(words))
            idx = error.get('unitIndex')
            if isinstance(idx, int) and 0 <= idx < len(targets) and targets[idx] == target:
                continue
            matches = [i for i, value in enumerate(targets) if value == target]
            if len(matches) == 1:
                error['unitIndex'] = matches[0]
                changes.append('unique_target_metadata_index')
            elif not isinstance(idx, int) or idx < 0 or idx >= len(targets):
                # An out-of-range repeated word can be recovered only if
                # valid, timestamped neighboring error anchors leave ONE
                # possible occurrence. Never choose the nearest occurrence.
                def seconds(entry):
                    m = re.match(r'^(\d{1,2}):(\d{2})(?:\.(\d+))?', str(entry.get('time', '')))
                    return int(m[1]) * 60 + int(m[2]) + float('0.' + (m[3] or '0')) if m else None
                times = [seconds(evidence[i]) for i in indexes]
                if any(t is None for t in times) or not matches:
                    continue
                low, high, anchors = -1, len(targets), 0
                for other in units.get('errors', []):
                    oi, links = other.get('unitIndex'), other.get('evidenceIndexes', [])
                    if other is error or not isinstance(oi, int) or not 0 <= oi < len(targets) or not links:
                        continue
                    if any(not isinstance(i, int) or not 0 <= i < len(evidence) or evidence[i].get('word') != targets[oi] for i in links):
                        continue
                    anchor_times = [seconds(evidence[i]) for i in links]
                    if any(t is None for t in anchor_times):
                        continue
                    if max(anchor_times) < min(times):
                        low, anchors = max(low, oi), anchors + 1
                    elif min(anchor_times) > max(times):
                        high, anchors = min(high, oi), anchors + 1
                candidates = [i for i in matches if low < i < high]
                if anchors and len(candidates) == 1:
                    error['unitIndex'] = candidates[0]
                    changes.append('unique_ordered_target_metadata_index')
    if fixed and len(grade.get('sections', [])) == 3 and grade.get('scoreLedger', {}).get('complete') is True:
        # Render corrections from the provider's structured acoustic evidence.
        # This resolves singular/plural or IPA discrepancies in duplicated
        # prose without inventing observations or deductions.
        groups = [('pronunciation', 'content'), ('intonation',), ('fluency',)]
        for section, types in zip(grade['sections'], groups):
            entries = [e for e in grade.get('evidence', []) if e.get('type') in types]
            original = section.get('correction', '')
            rendered = '\n'.join(
                f"{e.get('time', '')}: " +
                (f"{e.get('word', '')} {e.get('ipa', '')} — " if e.get('word') else '') +
                str(e.get('correction', '')) for e in entries
            )
            section['correction'] = original + ('\n' if original and rendered else '') + rendered
        changes.append('corrections_preserved_and_evidence_appended')
    return {'grade': grade, 'changes': sorted(set(changes)), 'version': 'offline-format-v2'}


if __name__ == '__main__':
    try:
        result = normalize(json.load(sys.stdin))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except Exception:
        print(json.dumps({'error': 'SHADOW_POSTPROCESS_INVALID_JSON'}))
        sys.exit(1)
