"""Domain-specific exceptions for Paperforge."""


class PaperforgeError(Exception):
    """Base class for expected application errors."""


class ArxivError(PaperforgeError):
    """Base error for arXiv integration failures."""


class ArxivTimeoutError(ArxivError):
    """The arXiv request exceeded its timeout."""


class ArxivResponseError(ArxivError):
    """The arXiv service returned an unusable response."""


class ArxivParseError(ArxivError):
    """The arXiv Atom response could not be parsed."""


class PdfDownloadError(PaperforgeError):
    """A PDF could not be downloaded or validated."""


class DocumentParsingError(PaperforgeError):
    """A local document could not be converted by Docling."""


class DocumentValidationError(DocumentParsingError):
    """A local document failed pre-conversion validation."""


class IngestionPipelineError(PaperforgeError):
    """The ingestion run could not complete its top-level operation."""


class SearchError(PaperforgeError):
    """Base error for search-index and query operations."""


class SearchIndexSchemaError(SearchError):
    """The configured OpenSearch index has an incompatible schema."""


class SearchUnavailableError(SearchError):
    """OpenSearch could not complete a search operation."""


class EmbeddingError(PaperforgeError):
    """Base error for embedding-provider operations."""


class EmbeddingUnavailableError(EmbeddingError):
    """Embedding generation is disabled or not configured."""


class EmbeddingResponseError(EmbeddingError):
    """The embedding provider returned an unusable response."""


class OllamaError(PaperforgeError):
    """Base error for Ollama connectivity and generation."""


class OllamaConnectionError(OllamaError):
    """The Ollama service could not be reached."""


class OllamaTimeoutError(OllamaError):
    """An Ollama request exceeded its configured timeout."""


class OllamaGenerationError(OllamaError):
    """Ollama returned an HTTP or response-format failure."""
