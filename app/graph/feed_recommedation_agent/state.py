"""
app/graph/feed_recommedation_agent/state.py
"""

from typing import Optional, Annotated
import operator
from typing_extensions import TypedDict


class FilteredSearchState(TypedDict):
    investor_id    : str
    filter_tags    : list[str]
    investor_vector: Optional[list[float]]
    candidates     : list[dict]
    final_results  : list[dict]
    errors         : Annotated[list[str], operator.add]