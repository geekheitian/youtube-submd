from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Glossary:
    preferred_terms: List[str]
    alias_map: Dict[str, str]
    keep_original: List[str]

    def to_prompt_hint(self) -> str:
        terms = '\n'.join(f'- {item}' for item in self.preferred_terms) or '- 无'
        aliases = '\n'.join(f'- {src} -> {dst}' for src, dst in self.alias_map.items()) or '- 无'
        keep_original = '\n'.join(f'- {item}' for item in self.keep_original) or '- 不确定时保留原词'
        return (
            f'频道术语：\n{terms}\n\n'
            f'常见纠错：\n{aliases}\n\n'
            f'保守规则：\n{keep_original}'
        )


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
    subtitle_strategy: str = 'native'
    glossary: Optional[Glossary] = None


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
    items: List[Dict[str, object]] = []
    current: Optional[Dict[str, object]] = None
    current_glossary: Optional[Dict[str, object]] = None
    current_glossary_list_key: Optional[str] = None
    current_glossary_dict_key: Optional[str] = None

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
                current_glossary = None
                current_glossary_list_key = None
                current_glossary_dict_key = None
                inline = stripped[2:].strip()
                if ':' in inline:
                    key, _, value = inline.partition(':')
                    _set_field(current, key.strip(), value.strip())
                continue

            if current is None:
                continue

            indent = len(line) - len(stripped)
            if indent == 4 and ':' in stripped:
                key, _, value = stripped.partition(':')
                key = key.strip()
                value = value.strip()
                if key == 'glossary' and not value:
                    current_glossary = {}
                    current['glossary'] = current_glossary
                    current_glossary_list_key = None
                    current_glossary_dict_key = None
                    continue
                _set_field(current, key, value)
                current_glossary = None
                current_glossary_list_key = None
                current_glossary_dict_key = None
                continue

            if current_glossary is None:
                continue

            if indent == 6 and ':' in stripped:
                key, _, value = stripped.partition(':')
                key = key.strip()
                value = value.strip()
                if not value:
                    if key in ('preferred_terms', 'keep_original'):
                        current_glossary[key] = []
                        current_glossary_list_key = key
                        current_glossary_dict_key = None
                    elif key == 'alias_map':
                        current_glossary[key] = {}
                        current_glossary_dict_key = key
                        current_glossary_list_key = None
                    continue
                current_glossary[key] = value.strip('"').strip("'")
                current_glossary_list_key = None
                current_glossary_dict_key = None
                continue

            if indent == 8 and stripped.startswith('- ') and current_glossary_list_key:
                value = stripped[2:].strip().strip('"').strip("'")
                cast_list = current_glossary.setdefault(current_glossary_list_key, [])
                if isinstance(cast_list, list):
                    cast_list.append(value)
                continue

            if indent == 8 and ':' in stripped and current_glossary_dict_key:
                key, _, value = stripped.partition(':')
                cast_dict = current_glossary.setdefault(current_glossary_dict_key, {})
                if isinstance(cast_dict, dict):
                    cast_dict[key.strip().strip('"').strip("'")] = value.strip().strip('"').strip("'")

    if current is not None:
        items.append(current)

    return _normalize_items(items)


def _set_field(item: Dict[str, object], key: str, raw_value: str) -> None:
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
        subtitle_strategy = _as_optional_string(item.get('subtitle_strategy')) or 'native'
        if subtitle_strategy not in ('native', 'asr_fallback'):
            subtitle_strategy = 'native'

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
                subtitle_strategy=subtitle_strategy,
                glossary=_parse_glossary(item.get('glossary')),
            )
        )

    return [item for item in result if item.enabled]


def _as_optional_string(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_string_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _as_optional_string(value)
    return [text] if text else []


def _as_string_dict(value: object) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: Dict[str, str] = {}
    for key, raw in value.items():
        clean_key = str(key).strip()
        clean_value = str(raw).strip()
        if clean_key and clean_value:
            result[clean_key] = clean_value
    return result


def _parse_glossary(raw: object) -> Optional[Glossary]:
    if not isinstance(raw, dict):
        return None
    glossary = Glossary(
        preferred_terms=_as_string_list(raw.get('preferred_terms')),
        alias_map=_as_string_dict(raw.get('alias_map')),
        keep_original=_as_string_list(raw.get('keep_original')),
    )
    if not glossary.preferred_terms and not glossary.alias_map and not glossary.keep_original:
        return None
    return glossary
