"""Validated keyword lists and source-specific literal query compilation."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchKeyword(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(min_length=1, max_length=500)
    match_mode: Literal['exact', 'fuzzy']

    @field_validator('text')
    @classmethod
    def normalized_text(cls, value):
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError('Keyword must contain ordinary nonblank text')
        return value


def display_query(keywords: list[SearchKeyword]) -> str:
    return ' / '.join(keyword.text for keyword in keywords)


def normalize_keywords(values) -> list[SearchKeyword]:
    if not isinstance(values, list) or not 1 <= len(values) <= 10:
        raise ValueError('Select one to ten keywords')
    result = [SearchKeyword.model_validate(value) for value in values]
    if len({keyword.text.lower() for keyword in result}) != len(result):
        raise ValueError('Keywords must be distinct ignoring case')
    if len(display_query(result).encode('utf-16-le')) // 2 > 500:
        raise ValueError('Keyword display query exceeds 500 UTF-16 units')
    return result


def _phrase(text: str) -> str:
    # Quotes and backslashes must not terminate a user-supplied literal phrase.
    return '"' + re.sub(r'(["\\*?~])', r'\\\1', text) + '"'


def _term(text: str) -> str:
    if text.upper() in ('AND', 'OR', 'NOT', 'ANDNOT', 'TO'):
        return _phrase(text)
    # Lucene query syntax is not user input syntax. Every reserved character is
    # escaped; generated AND operators are the only active operators.
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/&|])', r'\\\1', text)


def compile_query(provider: str, values) -> str:
    keywords = normalize_keywords(values)
    if provider == 'crossref':
        if any(keyword.match_mode == 'exact' for keyword in keywords):
            raise ValueError('Crossref does not guarantee exact phrase matching')
        # Crossref bibliographic query is broad text matching, not Boolean AND.
        return ' '.join(keyword.text for keyword in keywords)
    if provider not in ('arxiv', 'openalex'):
        raise ValueError('Unsupported keyword search provider')
    prefix = 'all:' if provider == 'arxiv' else ''
    parts = []
    for keyword in keywords:
        if keyword.match_mode == 'exact':
            parts.append(prefix + _phrase(keyword.text))
        else:
            parts.extend(prefix + _term(term) for term in keyword.text.split())
    return ' AND '.join(parts)
