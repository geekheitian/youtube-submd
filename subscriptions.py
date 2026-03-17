from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Subscription:
    platform: str
    name: str
    url: str
    limit: int = 5
    enabled: bool = True
    cookies_file: Optional[str] = None
    cookies_from_browser: Optional[str] = None
    summary_provider: Optional[str] = None


def load_subscriptions(config_path: Optional[Path] = None) -> List[Subscription]:
    candidates: List[Path] = []
    if config_path:
        candidates.append(config_path)
    root = Path(__file__).parent
    candidates.append(root / 'subscriptions.yaml')
    candidates.append(root / 'channels.yaml')
    candidates.append(Path.cwd() / 'subscriptions.yaml')
    candidates.append(Path.cwd() / 'channels.yaml')

    for path in candidates:
        if path.is_file():
            items = _parse_yaml(path)
            if items:
                return items
    return []


def _parse_yaml(path: Path) -> List[Subscription]:
    try:
        import yaml  # type: ignore

        with path.open(encoding='utf-8') as handle:
            data = yaml.safe_load(handle) or {}
        raw_subscriptions = data.get('subscriptions')
        if raw_subscriptions is None:
            raw_subscriptions = data.get('channels', [])
        return _normalize_items(raw_subscriptions or [])
    except ImportError:
        return _parse_yaml_manual(path)


def _parse_yaml_manual(path: Path) -> List[Subscription]:
    items: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None

    with path.open(encoding='utf-8') as handle:
        for raw_line in handle:
            line = raw_line.rstrip()
            stripped = line.lstrip()
            if not stripped or stripped.startswith('#'):
                continue

            if stripped in ('subscriptions:', 'channels:'):
                continue

            if line.startswith('  - '):
                if current is not None:
                    items.append(current)
                current = {}
                inline = stripped[2:].strip()
                if ':' in inline:
                    key, _, value = inline.partition(':')
                    _set_field(current, key.strip(), value.strip())
                continue

            if current is not None and line.startswith('    ') and ':' in stripped:
                key, _, value = stripped.partition(':')
                _set_field(current, key.strip(), value.strip())

    if current is not None:
        items.append(current)

    return _normalize_items(items)


def _set_field(item: Dict[str, str], key: str, raw_value: str) -> None:
    item[key] = raw_value.strip().strip('"').strip("'")


def _normalize_items(items: List[Dict[str, object]]) -> List[Subscription]:
    result: List[Subscription] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get('url', '')).strip()
        if not url:
            continue
        platform = str(item.get('platform', '')).strip().lower() or 'youtube'
        name = str(item.get('name', '')).strip() or platform
        enabled_raw = str(item.get('enabled', 'true')).strip().lower()
        enabled = enabled_raw not in ('false', '0', 'no')
        try:
            limit = int(str(item.get('limit', '5')).strip() or '5')
        except ValueError:
            limit = 5

        result.append(
            Subscription(
                platform=platform,
                name=name,
                url=url,
                limit=limit,
                enabled=enabled,
                cookies_file=_as_optional_string(item.get('cookies_file')),
                cookies_from_browser=_as_optional_string(item.get('cookies_from_browser')),
                summary_provider=_as_optional_string(item.get('summary_provider')),
            )
        )

    return [item for item in result if item.enabled]


def _as_optional_string(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
