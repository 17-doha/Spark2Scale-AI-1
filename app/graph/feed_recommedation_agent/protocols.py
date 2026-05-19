"""
Protocols — Dependency Inversion Abstractions
==============================================
Lightweight ``typing.Protocol`` abstractions for infrastructure dependencies.

These define the *contracts* that business logic depends on, rather than
concrete implementations (Qdrant, Neo4j, Supabase singletons). This enables:
  - Easier unit testing (swap in fakes/mocks)
  - Future backend migration without touching business logic
  - Clear documentation of what each consumer actually needs

No runtime cost — Protocol classes are erased at runtime.
"""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """Contract for vector database operations (currently backed by Qdrant)."""

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        limit: int,
        with_payload: bool = True,
        query_filter: Any = None,
    ) -> Any:
        """ANN similarity search returning scored points."""
        ...

    def upsert(self, collection_name: str, points: list[Any]) -> None:
        """Insert or update points in a collection."""
        ...

    def retrieve(
        self,
        collection_name: str,
        ids: list[str],
        with_vectors: bool = False,
        with_payload: bool = False,
    ) -> list[Any]:
        """Fetch specific points by ID."""
        ...

    def scroll(
        self,
        collection_name: str,
        scroll_filter: Any = None,
        with_vectors: bool = False,
        with_payload: bool = False,
        limit: int = 100,
    ) -> tuple[list[Any], Optional[str]]:
        """Paginated scan of a collection."""
        ...

    def set_payload(
        self,
        collection_name: str,
        payload: dict,
        points: list[str],
    ) -> None:
        """Update payload fields on existing points."""
        ...


@runtime_checkable
class TagRepository(Protocol):
    """Contract for fetching investor tag data (currently backed by Supabase)."""

    def fetch_investor_tags(self, investor_id: str) -> list[str]:
        """Return tag list for a single investor."""
        ...

    def fetch_all_investors(self) -> list[dict]:
        """Return all investor rows (user_id + tags)."""
        ...

    def fetch_unique_tags(self) -> list[str]:
        """Return de-duplicated union of all tags across every investor."""
        ...


@runtime_checkable
class GraphDBProtocol(Protocol):
    """Contract for graph database read/write operations (currently backed by Neo4j)."""

    def get_investor_subtags(
        self,
        user_id: str,
        hate_threshold: float = 0.01,
        limit: int = 50,
    ) -> list[str]:
        """Retrieve UCB-scored subtags for an investor."""
        ...

    def get_sibling_subtags(
        self,
        subtag_names: list[str],
        exclude: Optional[list[str]] = None,
        limit: int = 30,
    ) -> list[str]:
        """Find sibling subtags sharing a parent tag."""
        ...

    def update_graph_edge_weights(
        self,
        user_id: str,
        tag_names: list[str],
        subtag_names: list[str],
        reward: float,
        alpha: float,
    ) -> None:
        """Apply RL reward updates to investor graph edges."""
        ...
