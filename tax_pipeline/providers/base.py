from __future__ import annotations

from pathlib import Path
from typing import Callable

from tax_pipeline.providers.shared.document import DocumentDescriptor
from tax_pipeline.providers.shared.schema import DocumentFacts


class DocumentHandler:
    def extract(self, relative_path: Path, pages: list[str], descriptor: DocumentDescriptor) -> DocumentFacts:
        raise NotImplementedError


class CallableDocumentHandler(DocumentHandler):
    def __init__(
        self,
        func: Callable[[Path, list[str]], DocumentFacts],
    ) -> None:
        self._func = func

    def extract(self, relative_path: Path, pages: list[str], descriptor: DocumentDescriptor) -> DocumentFacts:
        return self._func(relative_path, pages)


class UnsupportedDocumentHandler(DocumentHandler):
    def extract(self, relative_path: Path, pages: list[str], descriptor: DocumentDescriptor) -> DocumentFacts:
        return DocumentFacts(
            relative_path=relative_path.as_posix(),
            doc_type=descriptor.doc_type,
            parser="deterministic.unsupported.v1",
            status="unsupported_doc_type",
            facts=[],
            warnings=[],
        )
