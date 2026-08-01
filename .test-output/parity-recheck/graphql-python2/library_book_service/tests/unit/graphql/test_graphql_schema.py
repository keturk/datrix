"""GraphQL schema smoke tests for library_book_service."""

from __future__ import annotations

import pytest

from library_book_service.graphql.schema import schema


@pytest.mark.unit
def test_graphql_schema_introspection() -> None:
    """GraphQL schema responds to introspection and exposes the Query root type."""
    result = schema.execute_sync("{ __typename }")
    assert result.errors is None, result.errors
    assert result.data == {"__typename": "Query"}


@pytest.mark.unit
def test_graphql_query_field_present_0() -> None:
    """Query root exposes field getBook."""
    q = """
    query IntrospectQueries {
      __schema {
        queryType {
          fields { name }
        }
      }
    }
    """
    result = schema.execute_sync(q)
    assert result.errors is None, result.errors
    assert result.data is not None
    fields = result.data["__schema"]["queryType"]["fields"]
    names = {f["name"] for f in fields}
    assert "getBook" in names, names


@pytest.mark.unit
def test_graphql_query_field_present_1() -> None:
    """Query root exposes field listBooks."""
    q = """
    query IntrospectQueries {
      __schema {
        queryType {
          fields { name }
        }
      }
    }
    """
    result = schema.execute_sync(q)
    assert result.errors is None, result.errors
    assert result.data is not None
    fields = result.data["__schema"]["queryType"]["fields"]
    names = {f["name"] for f in fields}
    assert "listBooks" in names, names


@pytest.mark.unit
def test_graphql_query_field_present_2() -> None:
    """Query root exposes field searchBooks."""
    q = """
    query IntrospectQueries {
      __schema {
        queryType {
          fields { name }
        }
      }
    }
    """
    result = schema.execute_sync(q)
    assert result.errors is None, result.errors
    assert result.data is not None
    fields = result.data["__schema"]["queryType"]["fields"]
    names = {f["name"] for f in fields}
    assert "searchBooks" in names, names


@pytest.mark.unit
def test_graphql_mutation_field_present_0() -> None:
    """Mutation root exposes field createBook."""
    q = """
    query IntrospectMutations {
      __schema {
        mutationType {
          fields { name }
        }
      }
    }
    """
    result = schema.execute_sync(q)
    assert result.errors is None, result.errors
    assert result.data is not None
    mutation_type = result.data["__schema"]["mutationType"]
    assert mutation_type is not None
    fields = mutation_type["fields"]
    names = {f["name"] for f in fields}
    assert "createBook" in names, names


@pytest.mark.unit
def test_graphql_mutation_field_present_1() -> None:
    """Mutation root exposes field updateBook."""
    q = """
    query IntrospectMutations {
      __schema {
        mutationType {
          fields { name }
        }
      }
    }
    """
    result = schema.execute_sync(q)
    assert result.errors is None, result.errors
    assert result.data is not None
    mutation_type = result.data["__schema"]["mutationType"]
    assert mutation_type is not None
    fields = mutation_type["fields"]
    names = {f["name"] for f in fields}
    assert "updateBook" in names, names


@pytest.mark.unit
def test_graphql_mutation_field_present_2() -> None:
    """Mutation root exposes field deleteBook."""
    q = """
    query IntrospectMutations {
      __schema {
        mutationType {
          fields { name }
        }
      }
    }
    """
    result = schema.execute_sync(q)
    assert result.errors is None, result.errors
    assert result.data is not None
    mutation_type = result.data["__schema"]["mutationType"]
    assert mutation_type is not None
    fields = mutation_type["fields"]
    names = {f["name"] for f in fields}
    assert "deleteBook" in names, names
