"""Present evidence IDs as document-wide citation numbers at the export boundary."""
import re

_BRACKETS = re.compile(r'\[([^\[\]\r\n]+)\]')
_INTERNAL = re.compile(r':p\d+:')
_SEPARATORS = re.compile(r'\s*[,;，；、]\s*|\s+(?=\S*:p\d+:)')


class StudyCitationFormatter:
    def __init__(self, report):
        self.by_paper = {}
        self.global_labels = {}
        self.unresolved = False
        counter = 0
        for item in report.analyses:
            labels = self.by_paper.setdefault(item.paper_id, {})
            for reference in item.citations:
                if reference.chunk_id in labels:
                    continue
                counter += 1
                labels[reference.chunk_id] = counter
                if reference.chunk_id in self.global_labels:
                    # A summary cannot disambiguate the same ID used by two papers.
                    self.global_labels[reference.chunk_id] = None
                else:
                    self.global_labels[reference.chunk_id] = counter

    def format(self, text: str, paper_id: str | None = None) -> str:
        labels = self.global_labels if paper_id is None else self.by_paper[paper_id]

        def replace(match):
            value = match.group(1).strip()
            if labels.get(value) is not None:
                return f'[{labels[value]}]'
            if not _INTERNAL.search(value):
                return match.group(0)  # Preserve ordinary math and existing numeric citations.
            parts = _SEPARATORS.split(value)
            if parts and all(labels.get(part) is not None for part in parts):
                return '[' + ', '.join(str(labels[part]) for part in dict.fromkeys(parts)) + ']'
            self.unresolved = True
            return '[引用待核对]'

        return _BRACKETS.sub(replace, text)
