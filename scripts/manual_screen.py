"""Reuse public manual facts only when the freshly fetched original is identical."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collect import digest
from screening import VERSION


def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('A verification timestamp needs a timezone')
    return result


def key(raw):
    return digest([raw['sourceUrl'], raw.get('roleKey', '')])


def fingerprint(raw):
    # Dates, role requirements, country, closure flags and completeness all count.
    # Listing labels and Greeting's header contain live D-day counters. The parser
    # already stores their relevant role, employment and deadline facts separately.
    return digest({k: v for k, v in raw.items() if k not in ('collectedAt', 'id', 'label', 'greetingHeader')})


def remember(job, cache):
    if job.get('screeningMode') != 'manual' or job.get('screeningVersion') != VERSION:
        return False
    try:
        raw = json.loads((cache / ('raw-' + key(job) + '.json')).read_text())
        if not raw.get('complete') or raw.get('id') != job['id'] or raw.get('sourceId') != job['sourceId']:
            return False
        if key(raw) != key(job) or stamp(job['lastVerifiedAt']) < stamp(raw['collectedAt']):
            return False
        record = {'version': VERSION, 'fingerprint': fingerprint(raw), 'job': job}
        path = cache / ('manual-' + key(job) + '.json')
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(record, ensure_ascii=False))
        temp.replace(path)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def reuse(raw, cache, now=None):
    if not raw.get('complete'):
        return None
    try:
        record = json.loads((cache / ('manual-' + key(raw) + '.json')).read_text())
        job = dict(record['job'])
        if record['version'] != VERSION or record['fingerprint'] != fingerprint(raw):
            return None
        if job['id'] != raw['id'] or job['sourceId'] != raw['sourceId'] or key(job) != key(raw):
            return None
        now = now or datetime.now(timezone.utc)
        expired = (job.get('deadlineAt') and stamp(job['deadlineAt']) <= now) or (
            job.get('deadlineDate') and job['deadlineDate'] < now.astimezone(ZoneInfo(job['deadlineTimezone'])).date().isoformat())
        if expired and job['status'] not in ('closed', 'excluded'):
            job.update(status='closed', evidence='검증된 접수 마감 경과')
        job['lastVerifiedAt'] = now.isoformat()
        return job
    except (OSError, ValueError, KeyError, TypeError):
        return None
