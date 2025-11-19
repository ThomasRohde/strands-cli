Here’s a minimal, self-contained `@tool` wrapper that:

* Uses the OpenAI Python SDK Vector Store **Search** API
* Is compatible with the **Strands Agents** SDK (`@tool` decorator)
* Does **no query rewriting** (`rewrite_query=False`)
* Returns an **XML string** with a clear, file_search-style structure and paging info

```python
from __future__ import annotations

from typing import Any, Dict, Optional

from openai import OpenAI
from strands import tool
from xml.sax.saxutils import escape as xml_escape

# Reuse a single client – Strands will typically run this inside a long-lived process.
client = OpenAI()  # Uses OPENAI_API_KEY from environment


def _esc_attr(value: Any) -> str:
    """Escape text for XML attributes."""
    return xml_escape(str(value), {'"': "&quot;"})


def _esc_text(value: Any) -> str:
    """Escape text for XML text nodes."""
    return xml_escape(str(value))


@tool
def file_search(
    query: str,
    vector_store_id: str,
    max_num_results: int = 10,
    next_page: Optional[str] = None,
    attribute_filter: Optional[Dict[str, Any]] = None,
    ranker: Optional[str] = None,
    score_threshold: Optional[float] = None,
) -> str:
    """
    Semantic search over a single OpenAI Vector Store using the Vector Store Search API
    (file_search-style retrieval, but without query rewriting).

    Use this tool to retrieve relevant chunks (snippets) from documents that have
    already been indexed into a vector store.

    Query language (no rewriting):
    - Provide `query` as a natural-language question or concise search phrase.
    - Mention domain concepts, document titles, sections, error messages, etc.
    - No query rewriting is performed: the string is sent to the Vector Store
      Search API unchanged.
    - Do NOT encode filters into the query text; use `attribute_filter` for
      metadata-based filtering.

    Attribute filter:
    - `attribute_filter` must follow the OpenAI Retrieval **attribute_filter**
      JSON shape and operates on vector_store.file attributes:
        * Comparison filter:
          {
            "type": "eq" | "ne" | "gt" | "gte" | "lt" | "lte",
            "property": "<attribute-key>",
            "value": <scalar-value>
          }
        * Compound filter:
          {
            "type": "and" | "or",
            "filters": [ <comparison-or-compound-filter>, ... ]
          }
    - Examples:
        * Restrict to region "us":
          {"type": "eq", "property": "region", "value": "us"}
        * Date range with unix timestamps:
          {
            "type": "and",
            "filters": [
              {"type": "gte", "property": "date", "value": 1704067200},
              {"type": "lte", "property": "date", "value": 1710892800}
            ]
          }

    Ranking options:
    - `ranker`:
        * "auto" to use OpenAI’s default ranking
        * Or a specific ranker ID (e.g. "default-2024-08-21")
    - `score_threshold`:
        * Float in [0.0, 1.0]; results with scores below this are filtered out.
        * Higher threshold => fewer but more relevant results.

    Paging:
    - `max_num_results`:
        * 1–50; defaults to 10.
    - `next_page`:
        * Opaque paging token returned by the API.
        * Leave empty / null for the first page.
        * For subsequent pages, call this tool again with the same
          `query` & `vector_store_id` but set `next_page` to the value
          returned in the previous XML response.

    XML output schema:
    - The tool ALWAYS returns a UTF-8 XML string with the following structure:

        <searchResults
            query="original or echoed query"
            vectorStoreId="..."
            hasMore="true|false"
            nextPage="next-page-token-or-empty">

          <result
              index="0-based-index-within-this-page"
              fileId="file-123"
              filename="document.txt"
              score="0.87">

            <attributes>
              <attribute name="region">us</attribute>
              <attribute name="author">Transport Authority</attribute>
              ...
            </attributes>

            <content>
              <chunk index="0" type="text">
                <text>First relevant text chunk...</text>
              </chunk>
              <chunk index="1" type="text">
                <text>Another relevant chunk...</text>
              </chunk>
              ...
            </content>

          </result>

          <!-- more <result> elements... -->

        </searchResults>

    - Error handling:
        * On failure, the tool returns:

          <searchResults error="true">
            <message>Short error message</message>
            <details>More technical details if available</details>
          </searchResults>

    Args:
        query:
            Natural-language search query. No query rewriting is applied.
        vector_store_id:
            ID of the OpenAI vector store to search.
        max_num_results:
            Maximum number of results in this page (1–50, default 10).
        next_page:
            Opaque cursor from a previous search response's `nextPage` attribute.
        attribute_filter:
            Optional metadata filter object using OpenAI's `attribute_filter` schema.
        ranker:
            Optional ranker identifier (e.g. "auto" or "default-2024-08-21").
        score_threshold:
            Optional relevance threshold in [0.0, 1.0]. Results below this score
            are excluded.

    Returns:
        XML string with search results formatted as described above.
    """
    try:
        ranking_options: Optional[Dict[str, Any]] = None
        if ranker is not None or score_threshold is not None:
            ranking_options = {}
            if ranker is not None:
                ranking_options["ranker"] = ranker
            if score_threshold is not None:
                ranking_options["score_threshold"] = score_threshold

        # Call OpenAI Vector Store Search API with query rewriting disabled
        result = client.vector_stores.search(
            vector_store_id=vector_store_id,
            query=query,
            max_num_results=max_num_results,
            next_page=next_page,
            attribute_filter=attribute_filter,
            ranking_options=ranking_options,
            rewrite_query=False,
        )

        # Convert to a plain dict so this keeps working even if the SDK’s
        # response model changes slightly.
        if hasattr(result, "to_dict"):
            data = result.to_dict()
        else:
            data = dict(result)  # type: ignore[arg-type]

        search_query = data.get("search_query", query)
        has_more = bool(data.get("has_more", False))
        next_page_token = data.get("next_page") or ""
        hits = data.get("data", []) or []

        xml_parts: list[str] = []

        xml_parts.append(
            f'<searchResults '
            f'query="{_esc_attr(search_query)}" '
            f'vectorStoreId="{_esc_attr(vector_store_id)}" '
            f'hasMore="{str(has_more).lower()}" '
            f'nextPage="{_esc_attr(next_page_token)}">'
        )

        for idx, hit in enumerate(hits):
            file_id = hit.get("file_id", "")
            filename = hit.get("filename", "")
            score = hit.get("score", 0.0)
            attributes = hit.get("attributes", {}) or {}
            content_items = hit.get("content", []) or []

            xml_parts.append(
                f'<result '
                f'index="{idx}" '
                f'fileId="{_esc_attr(file_id)}" '
                f'filename="{_esc_attr(filename)}" '
                f'score="{_esc_attr(score)}">'
            )

            # Attributes
            xml_parts.append("<attributes>")
            for key, value in attributes.items():
                xml_parts.append(
                    f'<attribute name="{_esc_attr(key)}">{_esc_text(value)}</attribute>'
                )
            xml_parts.append("</attributes>")

            # Content chunks
            xml_parts.append("<content>")
            for c_idx, chunk in enumerate(content_items):
                c_type = chunk.get("type", "")
                # For now we assume text chunks; you can extend this if OpenAI
                # adds other content types here.
                text_value = chunk.get("text", "")
                xml_parts.append(
                    f'<chunk index="{c_idx}" type="{_esc_attr(c_type)}">'
                    f'<text>{_esc_text(text_value)}</text>'
                    f"</chunk>"
                )
            xml_parts.append("</content>")

            xml_parts.append("</result>")

        xml_parts.append("</searchResults>")

        return "".join(xml_parts)

    except Exception as exc:
        # Always return valid XML, even on error
        return (
            "<searchResults error=\"true\">"
            f"<message>OpenAI vector store search failed</message>"
            f"<details>{_esc_text(repr(exc))}</details>"
            "</searchResults>"
        )
```

You can plug this directly into a Strands agent:

```python
from strands import Agent
from my_tools_module import openai_vector_store_search

agent = Agent(
    model="openai/gpt-4.1-mini",
    tools=[file_search],
)

response = agent("Find policies about woodchucks in North America.")
print(response)
```

