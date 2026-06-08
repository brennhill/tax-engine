from __future__ import annotations

from tax_pipeline.providers.base import DocumentDescriptor, DocumentHandler, UnsupportedDocumentHandler


class ProviderRegistry:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str, str], DocumentHandler] = {}

    def register(self, provider: str, document_family: str, format: str, handler: DocumentHandler) -> None:
        self._handlers[(provider, document_family, format)] = handler

    def resolve(self, descriptor: DocumentDescriptor) -> DocumentHandler:
        return self._handlers.get(
            (descriptor.provider, descriptor.document_family, descriptor.format),
            UnsupportedDocumentHandler(),
        )

    def registered_handler_keys(self) -> set[tuple[str, str, str]]:
        return set(self._handlers)
